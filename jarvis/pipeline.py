"""Upload -> extract -> redact -> Gemini -> save. Raw text is never persisted."""
from __future__ import annotations

import hashlib
import logging
import mimetypes
from pathlib import Path
from typing import Any

from jarvis import ai, repo
from jarvis.extract import ExtractError, extract_text
from jarvis.quiz_parser import parse_quiz_output

log = logging.getLogger(__name__)


def process_upload(user_id: str, filename: str, data: bytes, task: str) -> dict[str, Any]:
    name = Path(filename).name
    file_id = repo.create_file(
        user_id, name, mimetypes.guess_type(name)[0] or "application/octet-stream",
        len(data), hashlib.sha256(data).hexdigest(), task,
    )
    stem = Path(name).stem.strip() or "Study material"
    try:
        text = ai.anonymize_text(extract_text(name, data))
        if not text.strip():
            raise ExtractError("No usable text remained after privacy filtering.")
        truncated = len(text) > ai.MAX_INPUT_CHARS
        output = ai.generate(text, task)
        if task == "revision_notes":
            repo.save_notes(user_id, file_id, f"Revision: {stem}", output)
        else:
            repo.save_quiz(user_id, file_id, f"Practice: {stem}", parse_quiz_output(output))
        return {"filename": name, "status": "completed", "truncated": truncated}
    except (ExtractError, ai.AIError) as exc:
        msg = str(exc)
    except ValueError:  # malformed quiz JSON from the model
        msg = "The AI returned a quiz in an unusable format. Please try again."
    except Exception:
        log.exception("Unexpected processing failure")
        msg = "Unexpected error while processing this file."
    repo.fail_file(user_id, file_id, msg)
    return {"filename": name, "status": "failed", "error": msg}
