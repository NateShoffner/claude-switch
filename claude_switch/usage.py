"""Usage data for a Claude Code profile.

Token counts come from local files; utilization percentages and exact reset
times come from Anthropic's unified rate-limit headers.

Sources (in priority order):
  1. anthropic-ratelimit-unified-* headers  — real percentages, exact reset times
     Obtained by making a minimal inference call using the OAuth token stored in
     .credentials.json inside each profile's config_dir.  Results cached for
     _RATE_LIMIT_TTL seconds so the selector stays fast.
  2. Profile config limits                  — weekly_token_limit / session_token_limit
     Manual fallback for API-key org users or when the OAuth token has expired.
  3. Token counts only                      — no percentage, just raw display
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

_API_BASE = "https://api.anthropic.com"
_API_VERSION = "2023-06-01"
_TIMEOUT = 6  # seconds
_RATE_LIMIT_TTL = 300  # cache unified headers for 5 minutes
_RATE_LIMIT_CACHE_FILE = ".rate-limit-cache.json"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class UsageData:
    tokens: int
    direct_pct: float | None = None   # from API rate-limit headers (0–100)
    limit: int | None = None           # from profile config (fallback)
    reset_at: datetime | None = None
    label: str = "week"

    @property
    def pct(self) -> float | None:
        if self.direct_pct is not None:
            return self.direct_pct
        if self.limit and self.limit > 0:
            return min(100.0, (self.tokens / self.limit) * 100)
        return None


@dataclass
class RateLimitInfo:
    """Parsed from anthropic-ratelimit-unified-* response headers."""
    session_pct: float         # 0–100
    session_reset_at: datetime
    week_pct: float            # 0–100
    week_reset_at: datetime


# ---------------------------------------------------------------------------
# Rate-limit headers via OAuth token  (primary source)
# ---------------------------------------------------------------------------

def fetch_rate_limits(config_dir: str, force: bool = False) -> RateLimitInfo | None:
    """Return current utilization from Anthropic's unified rate-limit headers.

    Makes a minimal haiku inference call (~1 token) using the OAuth token stored
    in .credentials.json.  Result is cached in .rate-limit-cache.json for
    _RATE_LIMIT_TTL seconds to keep the selector fast.
    """
    cache_path = Path(config_dir) / _RATE_LIMIT_CACHE_FILE

    if not force:
        cached = _load_rate_cache(cache_path)
        if cached is not None:
            return cached

    token = _read_oauth_token(config_dir)
    if not token:
        return None

    body = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "x"}],
    }).encode()

    req = urllib.request.Request(
        f"{_API_BASE}/v1/messages",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            h = resp.headers
            info = _parse_rate_limit_headers(h)
            if info:
                _save_rate_cache(cache_path, info)
            return info
    except urllib.error.HTTPError as e:
        log.debug("Rate-limit fetch returned HTTP %s", e.code)
        # Headers may still be present even on error responses
        try:
            info = _parse_rate_limit_headers(e.headers)
            if info:
                _save_rate_cache(cache_path, info)
                return info
        except Exception:
            pass
    except Exception as e:
        log.debug("Rate-limit fetch failed: %s", e)
    return None


def _read_oauth_token(config_dir: str) -> str | None:
    creds_path = Path(config_dir) / ".credentials.json"
    if not creds_path.exists():
        return None
    try:
        creds = json.loads(creds_path.read_text(encoding="utf-8"))
        oauth = creds.get("claudeAiOauth", {})
        token = oauth.get("accessToken")
        expires_at_ms = oauth.get("expiresAt", 0)
        if expires_at_ms and time.time() * 1000 > expires_at_ms:
            log.debug("OAuth token has expired")
            return None
        return token or None
    except Exception as e:
        log.debug("Failed to read credentials: %s", e)
        return None


def _parse_rate_limit_headers(headers) -> RateLimitInfo | None:
    try:
        session_pct_raw = headers.get("anthropic-ratelimit-unified-5h-utilization")
        session_reset_raw = headers.get("anthropic-ratelimit-unified-5h-reset")
        week_pct_raw = headers.get("anthropic-ratelimit-unified-7d-utilization")
        week_reset_raw = headers.get("anthropic-ratelimit-unified-7d-reset")

        if not all([session_pct_raw, session_reset_raw, week_pct_raw, week_reset_raw]):
            return None

        return RateLimitInfo(
            session_pct=float(session_pct_raw) * 100,
            session_reset_at=datetime.fromtimestamp(int(session_reset_raw), tz=timezone.utc),
            week_pct=float(week_pct_raw) * 100,
            week_reset_at=datetime.fromtimestamp(int(week_reset_raw), tz=timezone.utc),
        )
    except Exception as e:
        log.debug("Failed to parse rate-limit headers: %s", e)
        return None


def _load_rate_cache(path: Path) -> RateLimitInfo | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - data.get("fetched_at", 0) > _RATE_LIMIT_TTL:
            return None
        return RateLimitInfo(
            session_pct=data["session_pct"],
            session_reset_at=datetime.fromtimestamp(data["session_reset_unix"], tz=timezone.utc),
            week_pct=data["week_pct"],
            week_reset_at=datetime.fromtimestamp(data["week_reset_unix"], tz=timezone.utc),
        )
    except Exception:
        return None


def _save_rate_cache(path: Path, info: RateLimitInfo) -> None:
    try:
        path.write_text(json.dumps({
            "fetched_at": time.time(),
            "session_pct": info.session_pct,
            "session_reset_unix": int(info.session_reset_at.timestamp()),
            "week_pct": info.week_pct,
            "week_reset_unix": int(info.week_reset_at.timestamp()),
        }), encoding="utf-8")
    except Exception as e:
        log.debug("Failed to write rate cache: %s", e)


# ---------------------------------------------------------------------------
# Token counts — local files
# ---------------------------------------------------------------------------

def fetch_local_usage(config_dir: str, weekly_limit: int | None = None) -> UsageData | None:
    """Read past-7-day token count from Claude Code's stats-cache.json."""
    cache_path = Path(config_dir) / "stats-cache.json"
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception as e:
        log.debug("Failed to read stats-cache.json: %s", e)
        return None

    cutoff = (date.today() - timedelta(days=7)).isoformat()
    total = 0
    for entry in data.get("dailyModelTokens", []):
        if entry.get("date", "") < cutoff:
            continue
        for tokens in entry.get("tokensByModel", {}).values():
            total += int(tokens)

    if total == 0:
        return None

    return UsageData(tokens=total, limit=weekly_limit, label="week")


def fetch_session_usage(config_dir: str, session_limit: int | None = None) -> UsageData | None:
    """Sum input+output tokens from assistant messages within the past 5 hours."""
    projects_dir = Path(config_dir) / "projects"
    if not projects_dir.exists():
        return None

    now = datetime.now(tz=timezone.utc)
    window_start = now - timedelta(hours=5)
    total = 0
    earliest_ts: datetime | None = None

    try:
        for jsonl in projects_dir.rglob("*.jsonl"):
            if jsonl.stat().st_mtime < window_start.timestamp():
                continue
            for line in jsonl.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") != "assistant":
                    continue
                ts_raw = obj.get("timestamp")
                if not ts_raw:
                    continue
                try:
                    ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                except Exception:
                    continue
                if ts < window_start:
                    continue
                msg = obj.get("message", {})
                if not isinstance(msg, dict) or "usage" not in msg:
                    continue
                u = msg["usage"]
                total += int(u.get("input_tokens", 0))
                total += int(u.get("output_tokens", 0))
                if earliest_ts is None or ts < earliest_ts:
                    earliest_ts = ts
    except Exception as e:
        log.debug("Failed to read session JSONL: %s", e)
        return None

    if total == 0:
        return None

    reset_at = (earliest_ts + timedelta(hours=5)) if earliest_ts else None
    return UsageData(tokens=total, limit=session_limit, reset_at=reset_at, label="session")


# ---------------------------------------------------------------------------
# Admin API — org API-key usage (optional, separate from subscription usage)
# ---------------------------------------------------------------------------

def fetch_api_usage(admin_api_key: str, weekly_limit: int | None = None) -> UsageData | None:
    """Fetch org API-key token usage from the Anthropic admin API.

    This reflects Anthropic API calls made via API keys, NOT Claude.ai
    subscription usage.  Docs: https://platform.claude.com/docs/en/manage-claude/usage-cost-api
    """
    end = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=7)
    params = urllib.parse.urlencode({
        "starting_at": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ending_at": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bucket_width": "1d",
    })
    req = urllib.request.Request(
        f"{_API_BASE}/v1/organizations/usage_report/messages?{params}",
        headers={"x-api-key": admin_api_key, "anthropic-version": _API_VERSION},
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
            total = sum(
                int(r.get("input_tokens", 0)) + int(r.get("output_tokens", 0))
                for b in data.get("data", []) if isinstance(b, dict)
                for r in b.get("results", []) if isinstance(r, dict)
            )
            if total == 0:
                return None
            reset_at = (end + timedelta(days=1))
            return UsageData(tokens=total, limit=weekly_limit, reset_at=reset_at, label="week")
    except Exception as e:
        log.debug("Admin API fetch failed: %s", e)
    return None


fetch_weekly_usage = fetch_api_usage  # backwards compat alias


# ---------------------------------------------------------------------------
# Formatting helpers (used by ui.py)
# ---------------------------------------------------------------------------

def fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)
