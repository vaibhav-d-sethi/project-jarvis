"""Aiven MySQL access via PyMySQL. One short-lived TLS connection per unit of work."""
from __future__ import annotations

import ssl
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pymysql
from pymysql.cursors import DictCursor

from jarvis import config

_SCHEMA = Path(__file__).resolve().parents[1] / "schema.sql"


def _ssl_context() -> ssl.SSLContext:
    """Verify the server certificate chain against the Aiven project CA.

    DB_SSL_CA may be the PEM text itself (easiest for Streamlit secrets) or a file path.
    Hostname checking is optional (DB_SSL_VERIFY_HOSTNAME=true), matching Aiven's VERIFY_CA mode.
    """
    ca = (config.get("DB_SSL_CA") or "").strip()
    if "BEGIN CERTIFICATE" in ca:
        ctx = ssl.create_default_context(cadata=ca)
    elif ca:
        ctx = ssl.create_default_context(cafile=ca)
    else:
        ctx = ssl.create_default_context()
    ctx.check_hostname = (config.get("DB_SSL_VERIFY_HOSTNAME", "false") or "").lower() == "true"
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


@contextmanager
def connection() -> Iterator[pymysql.connections.Connection]:
    """Yield a connection; commit on success, roll back on error, always close."""
    conn = pymysql.connect(
        host=config.require("DB_HOST"),
        port=int(config.get("DB_PORT", "3306") or 3306),
        user=config.require("DB_USER"),
        password=config.require("DB_PASSWORD"),
        database=config.require("DB_NAME"),
        charset="utf8mb4",
        cursorclass=DictCursor,
        ssl=_ssl_context(),
        connect_timeout=10,
        read_timeout=30,
        write_timeout=30,
        autocommit=False,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_schema() -> None:
    """Create tables if missing and upgrade ones left by the old JARVIS version."""
    statements = [s.strip() for s in _SCHEMA.read_text(encoding="utf-8").split(";")]
    with connection() as conn, conn.cursor() as cur:
        for stmt in statements:
            body = "\n".join(l for l in stmt.splitlines() if not l.strip().startswith("--")).strip()
            if body:
                cur.execute(body)
        cur.execute(
            "SELECT COLUMN_NAME AS c FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='user_files'"
        )
        cols = {r["c"] for r in cur.fetchall()}
        if "task" not in cols:
            cur.execute(
                "ALTER TABLE user_files ADD COLUMN task "
                "ENUM('revision_notes','quiz_generation') NOT NULL DEFAULT 'revision_notes'"
            )
        if "error_message" not in cols:
            cur.execute("ALTER TABLE user_files ADD COLUMN error_message VARCHAR(500) NULL")
