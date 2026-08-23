"""Allowlisted SPA localStorage capture — never tokens in plaintext logs."""

from __future__ import annotations

import os
from typing import Any


DEFAULT_ALLOWLIST = ("theme", "locale", "ui.prefs", "feature.flags")


def allowlisted_storage_keys() -> list[str]:
    raw = os.environ.get("WEBTWIN_STORAGE_ALLOWLIST", "")
    if raw.strip():
        return [key.strip() for key in raw.split(",") if key.strip()]
    return list(DEFAULT_ALLOWLIST)


def capture_allowlisted_local_storage(page) -> dict[str, Any]:
    keys = allowlisted_storage_keys()
    try:
        return page.evaluate(
            """(keys) => {
              const out = {};
              for (const key of keys) {
                try {
                  const value = localStorage.getItem(key);
                  if (value != null) {
                    const lower = key.toLowerCase();
                    if (lower.includes('token') || lower.includes('jwt') || lower.includes('secret')) {
                      out[key] = '[REDACTED]';
                    } else {
                      out[key] = value.slice(0, 200);
                    }
                  }
                } catch (e) {}
              }
              return out;
            }""",
            keys,
        )
    except Exception:
        return {}
