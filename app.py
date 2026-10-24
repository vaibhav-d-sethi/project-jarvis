"""Project JARVIS: the whole app (UI + backend logic) as one Streamlit process.

Run:  streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

from jarvis import auth, db, repo
from jarvis.extract import ALLOWED_EXTENSIONS
from jarvis.pipeline import process_upload

st.set_page_config(page_title="Project JARVIS", page_icon="📚", layout="wide")

MAX_FILES, MAX_TOTAL_MB = 10, 40


@st.cache_resource(show_spinner="Connecting to database...")
def _init_db() -> bool:
    db.ensure_schema()
    return True


try:
    _init_db()
except Exception as exc:  # misconfigured secrets, wrong CA, network, etc.
    st.title("📚 Project JARVIS")
    st.error("Cannot connect to the database. Check your DB_* secrets and Aiven CA certificate.")
    st.caption(f"{type(exc).__name__}: {exc}")
    st.stop()

st.title("📚 Project JARVIS")
st.caption("Journal & Automated Revision Virtual Intelligence System")

user = auth.current_user()
if user is None:
    auth.render_login()
    st.stop()

pages = ["Dashboard", "Upload & generate", "Revision notes", "Practice quizzes"]
if user["role"] == "admin":
    pages.append("Admin")
with st.sidebar:
    page = st.radio("Section", pages, label_visibility="collapsed")
    st.divider()
    st.caption(f"Signed in as {user['email']}")
    if st.button("Sign out", use_container_width=True):
        auth.logout()
        st.rerun()


def dashboard() -> None:
    s = repo.dashboard_stats(user["id"])
    a, b, c, d = st.columns(4)
    a.metric("Revision notes", s["notes"])
    b.metric("Quizzes", s["quizzes"])
    c.metric("Quiz attempts", s["attempts"])
    d.metric("Average score", f"{s['avg_pct']}%" if s["avg_pct"] is not None else "n/a")
    st.subheader("Recent uploads")
    if s["recent"]:
        st.dataframe(
            [{"File": r["original_filename"], "Generated": r["task"].replace("_", " "),
              "Status": r["status"], "Note": r["error_message"] or "", "When": str(r["created_at"])}
             for r in s["recent"]],
            hide_index=True, use_container_width=True,
        )
    else:
        st.info("Nothing yet. Open **Upload & generate** to start.")


def upload() -> None:
    st.subheader("Upload study materials")
    label = st.selectbox("What should JARVIS generate?", ["Revision notes", "Practice quiz"])
    task = "revision_notes" if label == "Revision notes" else "quiz_generation"
    files = st.file_uploader(
        "Choose files", type=sorted(e.lstrip(".") for e in ALLOWED_EXTENSIONS), accept_multiple_files=True,
        help=f"Up to {MAX_FILES} files, {MAX_TOTAL_MB} MB combined. Scanned PDFs and images are OCRed.",
    )
    consent = st.checkbox(
        "I understand extracted text is sent to Google Gemini after automated redaction. Redaction is "
        "heuristic and cannot guarantee removal of every personal identifier."
    )
    if not st.button("Generate", type="primary", disabled=not files):
        return
    if not consent:
        st.warning("Please confirm the AI processing notice first.")
        return
    if len(files) > MAX_FILES or sum(f.size for f in files) > MAX_TOTAL_MB * 1024 * 1024:
        st.error(f"Limit: {MAX_FILES} files and {MAX_TOTAL_MB} MB combined.")
        return
    bar = st.progress(0.0)
    for i, f in enumerate(files):
        with st.spinner(f"Processing {f.name} ({i + 1}/{len(files)})..."):
            res = process_upload(user["id"], f.name, f.getvalue(), task)
        if res["status"] == "completed":
            st.success(f"{f.name}: done." + (" (Only the first 100,000 characters were used.)" if res["truncated"] else ""))
        else:
            st.error(f"{f.name}: {res['error']}")
        bar.progress((i + 1) / len(files))
    st.caption("Open the matching section in the sidebar to review the results.")


def notes() -> None:
    st.subheader("Revision notes")
    items = repo.list_notes(user["id"])
    if not items:
        st.info("No notes yet.")
        return
    i = st.selectbox("Choose a note", range(len(items)), format_func=lambda k: items[k]["title"])
    note = items[i]
    st.caption(f"Created {note['created_at']}")
    st.markdown(note["content"])
    st.download_button("Download (.md)", note["content"], file_name=f"{note['title']}.md", mime="text/markdown")


def quizzes() -> None:
    st.subheader("Practice quizzes")
    items = repo.list_quizzes(user["id"])
    if not items:
        st.info("No quizzes yet.")
        return
    i = st.selectbox("Choose a quiz", range(len(items)), format_func=lambda k: items[k]["title"])
    quiz = items[i]
    questions = repo.get_quiz_questions(user["id"], quiz["id"])  # answers stay server-side
    result_key = f"result_{quiz['id']}"
    with st.form(f"quiz_{quiz['id']}"):
        picked: dict[str, str | None] = {}
        for n, q in enumerate(questions, start=1):
            st.markdown(f"**{n}. {q['question_text']}**")
            opts = {"A": q["option_a"], "B": q["option_b"], "C": q["option_c"], "D": q["option_d"]}
            picked[q["id"]] = st.radio(
                "Answer", list(opts), index=None, format_func=lambda L, o=opts: f"{L}. {o[L]}",
                key=f"ans_{q['id']}", label_visibility="collapsed",
            )
        submitted = st.form_submit_button("Submit answers", type="primary")
    if submitted:
        st.session_state[result_key] = repo.record_attempt(user["id"], quiz["id"], picked)
    res = st.session_state.get(result_key)
    if res:
        st.success(f"Score: {res['score']} / {res['total']}")
        by_id = {r["id"]: r for r in res["results"]}
        for n, q in enumerate(questions, start=1):
            r = by_id[q["id"]]
            icon = "✅" if r["is_correct"] else "❌"
            with st.expander(f"{icon} Question {n}"):
                st.write(f"Your answer: {r['chosen'] or 'none'} · Correct: {r['correct']}")
                if r["explanation"]:
                    st.write(r["explanation"])


def admin() -> None:
    st.subheader("Accounts")
    for u in repo.list_users():
        cols = st.columns([4, 1, 1])
        cols[0].write(f"**{u['email']}** · {u['role']}")
        cols[1].write("Active" if u["is_active"] else "Inactive")
        if cols[2].button("Deactivate" if u["is_active"] else "Activate", key=f"adm_{u['id']}",
                          disabled=(u["id"] == user["id"])):
            try:
                repo.set_user_active(u["id"], not u["is_active"])
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


{"Dashboard": dashboard, "Upload & generate": upload, "Revision notes": notes,
 "Practice quizzes": quizzes, "Admin": admin}[page]()
