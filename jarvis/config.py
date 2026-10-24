"""Configuration from Streamlit secrets, falling back to environment variables."""
from __future__ import annotations

import os


def get(key: str, default: str | None = None) -> str | None:
    try:
        import streamlit as st

        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:  # no secrets file, or running outside Streamlit
        pass
    return os.environ.get(key, default)


def require(key: str) -> str:
    value = get(key)
    if not value or not value.strip():
        raise RuntimeError(f"Missing required setting: {key}")
    return value.strip()


def admin_emails() -> set[str]:
    raw = get("ADMIN_EMAILS", "") or ""
    return {e.strip().lower() for e in raw.split(",") if e.strip()}
