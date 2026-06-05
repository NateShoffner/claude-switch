"""Secure admin API key resolution.

Resolution order per profile:
  1. OS keychain  (Windows Credential Manager / macOS Keychain / Linux Secret Service)
  2. Environment variable  (profile.admin_api_key_env → os.environ[name])
  3. Plaintext config  (profile.admin_api_key — least secure, stored in ~/claude-switch.json)

Keychain access requires the optional 'keyring' package:
    pip install keyring
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

_SERVICE = "claude-switch"


def get_admin_key(profile_key: str, profile) -> str | None:
    key = _from_keychain(profile_key)
    if key:
        return key

    if profile.admin_api_key_env:
        key = os.environ.get(profile.admin_api_key_env)
        if key:
            return key
        log.debug("Env var %s not set for profile %s", profile.admin_api_key_env, profile_key)

    return profile.admin_api_key or None


def store_in_keychain(profile_key: str, api_key: str) -> bool:
    try:
        import keyring

        keyring.set_password(_SERVICE, profile_key, api_key)
        return True
    except ImportError:
        return False
    except Exception as e:
        log.debug("keyring store failed: %s", e)
        return False


def remove_from_keychain(profile_key: str) -> bool:
    try:
        import keyring
        import keyring.errors

        keyring.delete_password(_SERVICE, profile_key)
        return True
    except ImportError:
        return False
    except Exception:
        return False


def keychain_available() -> bool:
    try:
        import keyring  # noqa: F401

        return True
    except ImportError:
        return False


def _from_keychain(profile_key: str) -> str | None:
    try:
        import keyring

        return keyring.get_password(_SERVICE, profile_key)
    except ImportError:
        return None
    except Exception as e:
        log.debug("keyring get failed: %s", e)
        return None
