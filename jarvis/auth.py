"""Registration, login and session handling for the Streamlit app.

The signed-in user lives in st.session_state (per browser tab). Every script run
re-reads the user row, so deactivating an account takes effect on its next click.
"""
from __future__ import annotations

import time

import streamlit as st

from jarvis import config, repo
from jarvis.security import DUMMY_HASH, AuthError, hash_password, normalize_email, verify_password

_MAX_FAILURES, _WINDOW_S = 5, 15 * 60


@st.cache_resource
def _failures() -> dict[str, list[float]]:
    return {}  # email -> timestamps of recent failed logins (shared across sessions)


def _throttled(email: str) -> bool:
    now = time.time()
    recent = [t for t in _failures().get(email, []) if now - t < _WINDOW_S]
    _failures()[email] = recent
    return len(recent) >= _MAX_FAILURES


def register(email: str, password: str) -> None:
    email = normalize_email(email)
    pw_hash = hash_password(password)  # validates length
    role = "admin" if email in config.admin_emails() else "user"
    try:
        repo.create_user(email, pw_hash, email.split("@")[0], role)
    except repo.EmailTaken as exc:
        raise AuthError("An account with this email already exists.") from exc


def login(email: str, password: str) -> dict:
    email = normalize_email(email)
    if _throttled(email):
        raise AuthError("Too many failed attempts. Try again in 15 minutes.")
    user = repo.get_user_with_hash(email)
    ok = verify_password(password, user["password_hash"] if user else DUMMY_HASH)
    if not user or not ok or not user["is_active"]:
        _failures().setdefault(email, []).append(time.time())
        raise AuthError("Email or password is incorrect.")
    user.pop("password_hash", None)
    st.session_state["user"] = user
    return user


def logout() -> None:
    st.session_state.clear()


def current_user() -> dict | None:
    """Return the fresh user row, or None (clearing the session) if gone/deactivated."""
    cached = st.session_state.get("user")
    if not cached:
        return None
    fresh = repo.get_user(cached["id"])
    if not fresh or not fresh["is_active"]:
        st.session_state.clear()
        return None
    st.session_state["user"] = fresh
    return fresh


def render_login() -> None:
    tab_in, tab_up = st.tabs(["Sign in", "Create account"])
    with tab_in, st.form("login"):
        email = st.text_input("Email")
        pw = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in", type="primary"):
            try:
                login(email, pw)
                st.rerun()
            except AuthError as exc:
                st.error(str(exc))
    with tab_up, st.form("register"):
        email = st.text_input("Email", key="reg_email")
        pw = st.text_input("Password (12+ characters)", type="password", key="reg_pw")
        if st.form_submit_button("Create account"):
            try:
                register(email, pw)
                st.success("Account created. Switch to the Sign in tab.")
            except AuthError as exc:
                st.error(str(exc))
