"""All SQL lives here. Every query is parameterized and scoped to the owning user."""
from __future__ import annotations

import json
import uuid
from typing import Any

import pymysql

from jarvis import db

_USER_COLS = "id, email, display_name, role, is_active, created_at"


class EmailTaken(Exception):
    pass


# ---------- users ----------
def create_user(email: str, password_hash: str, display_name: str, role: str = "user") -> str:
    uid = str(uuid.uuid4())
    try:
        with db.connection() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO users (id, email, password_hash, display_name, role) VALUES (%s,%s,%s,%s,%s)",
                (uid, email, password_hash, display_name[:100], role),
            )
    except pymysql.err.IntegrityError as exc:
        raise EmailTaken from exc
    return uid


def get_user_with_hash(email: str) -> dict[str, Any] | None:
    with db.connection() as c, c.cursor() as cur:
        cur.execute(f"SELECT {_USER_COLS}, password_hash FROM users WHERE email=%s", (email,))
        return cur.fetchone()


def get_user(user_id: str) -> dict[str, Any] | None:
    with db.connection() as c, c.cursor() as cur:
        cur.execute(f"SELECT {_USER_COLS} FROM users WHERE id=%s", (user_id,))
        return cur.fetchone()


def list_users() -> list[dict[str, Any]]:
    with db.connection() as c, c.cursor() as cur:
        cur.execute(f"SELECT {_USER_COLS} FROM users ORDER BY created_at DESC LIMIT 500")
        return list(cur.fetchall())


def set_user_active(user_id: str, active: bool) -> None:
    """Refuses to leave the system without an active admin."""
    with db.connection() as c, c.cursor() as cur:
        cur.execute("SELECT role, is_active FROM users WHERE id=%s FOR UPDATE", (user_id,))
        target = cur.fetchone()
        if target is None:
            raise ValueError("User not found.")
        if not active and target["role"] == "admin" and target["is_active"]:
            cur.execute("SELECT COUNT(*) AS n FROM users WHERE role='admin' AND is_active=TRUE")
            if cur.fetchone()["n"] <= 1:
                raise ValueError("At least one active administrator must remain.")
        cur.execute("UPDATE users SET is_active=%s WHERE id=%s", (active, user_id))


# ---------- files / jobs ----------
def create_file(user_id: str, filename: str, mime: str, size: int, sha256: str, task: str) -> str:
    fid = str(uuid.uuid4())
    with db.connection() as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO user_files (id,user_id,original_filename,mime_type,file_size_bytes,sha256_hash,task) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (fid, user_id, filename[:255], mime[:127], size, sha256, task),
        )
    return fid


def fail_file(user_id: str, file_id: str, message: str) -> None:
    with db.connection() as c, c.cursor() as cur:
        cur.execute(
            "UPDATE user_files SET status='failed', error_message=%s WHERE id=%s AND user_id=%s",
            (message[:500], file_id, user_id),
        )


def save_notes(user_id: str, file_id: str, title: str, content: str) -> str:
    nid = str(uuid.uuid4())
    with db.connection() as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO revision_notes (id,user_id,file_id,title,content) VALUES (%s,%s,%s,%s,%s)",
            (nid, user_id, file_id, title[:255], content),
        )
        cur.execute("UPDATE user_files SET status='completed' WHERE id=%s AND user_id=%s", (file_id, user_id))
    return nid


def save_quiz(user_id: str, file_id: str, title: str, questions: list[dict[str, Any]]) -> str:
    qid = str(uuid.uuid4())
    with db.connection() as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO quizzes (id,user_id,file_id,title,total_questions) VALUES (%s,%s,%s,%s,%s)",
            (qid, user_id, file_id, title[:255], len(questions)),
        )
        cur.executemany(
            "INSERT INTO quiz_questions (id,quiz_id,question_order,question_text,option_a,option_b,option_c,"
            "option_d,correct_option,explanation) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            [
                (str(uuid.uuid4()), qid, i, q["question"], *q["options"], q["correct_option"], q["explanation"] or None)
                for i, q in enumerate(questions, start=1)
            ],
        )
        cur.execute("UPDATE user_files SET status='completed' WHERE id=%s AND user_id=%s", (file_id, user_id))
    return qid


# ---------- reading ----------
def list_notes(user_id: str) -> list[dict[str, Any]]:
    with db.connection() as c, c.cursor() as cur:
        cur.execute(
            "SELECT id,title,content,created_at FROM revision_notes WHERE user_id=%s "
            "ORDER BY created_at DESC LIMIT 200",
            (user_id,),
        )
        return list(cur.fetchall())


def list_quizzes(user_id: str) -> list[dict[str, Any]]:
    with db.connection() as c, c.cursor() as cur:
        cur.execute(
            "SELECT id,title,total_questions,created_at FROM quizzes WHERE user_id=%s "
            "ORDER BY created_at DESC LIMIT 200",
            (user_id,),
        )
        return list(cur.fetchall())


def get_quiz_questions(user_id: str, quiz_id: str, include_answers: bool = False) -> list[dict[str, Any]]:
    """Questions of a quiz the user owns. Correct answers are excluded unless requested."""
    extra = ", q.correct_option, q.explanation" if include_answers else ""
    with db.connection() as c, c.cursor() as cur:
        cur.execute(
            f"SELECT q.id, q.question_text, q.option_a, q.option_b, q.option_c, q.option_d{extra} "
            "FROM quiz_questions q JOIN quizzes z ON z.id=q.quiz_id "
            "WHERE q.quiz_id=%s AND z.user_id=%s ORDER BY q.question_order",
            (quiz_id, user_id),
        )
        return list(cur.fetchall())


def record_attempt(user_id: str, quiz_id: str, answers: dict[str, str | None]) -> dict[str, Any]:
    """Score answers on the server and store the attempt."""
    questions = get_quiz_questions(user_id, quiz_id, include_answers=True)
    if not questions:
        raise ValueError("Quiz not found.")
    results, score = [], 0
    for q in questions:
        chosen = answers.get(q["id"])
        ok = chosen == q["correct_option"]
        score += ok
        results.append({"id": q["id"], "chosen": chosen, "correct": q["correct_option"],
                        "is_correct": ok, "explanation": q["explanation"]})
    with db.connection() as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO quiz_attempts (id,user_id,quiz_id,score,total_questions,answers_json) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (str(uuid.uuid4()), user_id, quiz_id, score, len(questions), json.dumps(answers)),
        )
    return {"score": score, "total": len(questions), "results": results}


def dashboard_stats(user_id: str) -> dict[str, Any]:
    with db.connection() as c, c.cursor() as cur:
        cur.execute("SELECT COUNT(*) n FROM revision_notes WHERE user_id=%s", (user_id,))
        notes = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) n FROM quizzes WHERE user_id=%s", (user_id,))
        quizzes = cur.fetchone()["n"]
        cur.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(score),0) s, COALESCE(SUM(total_questions),0) t "
            "FROM quiz_attempts WHERE user_id=%s",
            (user_id,),
        )
        a = cur.fetchone()
        cur.execute(
            "SELECT original_filename, task, status, error_message, created_at FROM user_files "
            "WHERE user_id=%s ORDER BY created_at DESC LIMIT 10",
            (user_id,),
        )
        recent = list(cur.fetchall())
    pct = round(100 * a["s"] / a["t"]) if a["t"] else None
    return {"notes": notes, "quizzes": quizzes, "attempts": a["n"], "avg_pct": pct, "recent": recent}
