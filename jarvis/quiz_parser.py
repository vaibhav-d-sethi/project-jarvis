"""Normalize and validate quiz JSON returned by Gemini."""
from __future__ import annotations

import json
import re
from typing import Any

_OPTION_PREFIX = re.compile(r"^\s*\(?[A-Da-d][\).:\-]\s*")
_LETTER_KEY = re.compile(r"^(?:option[_\s-]*)?([a-d])$", re.IGNORECASE)
_ANSWER_PREFIX = re.compile(r"^(?:OPTION\s+)?([ABCD])(?:\b|[.):])", re.IGNORECASE)


def _option_text(value: Any) -> str:
    """Extract display text from a string or common structured option object."""
    if isinstance(value, dict):
        for key in ("text", "option", "value", "answer", "content", "label"):
            candidate = value.get(key)
            if isinstance(candidate, (str, int, float)):
                value = candidate
                break
        else:
            scalar_values = [v for v in value.values() if isinstance(v, (str, int, float))]
            value = scalar_values[-1] if scalar_values else ""
    if not isinstance(value, (str, int, float)):
        return ""
    return _OPTION_PREFIX.sub("", str(value)).strip()


def _normalize_options(raw_options: Any) -> list[str]:
    """Return four options in A/B/C/D order when the response shape is recoverable."""
    if isinstance(raw_options, dict):
        by_letter: dict[str, str] = {}
        for key, value in raw_options.items():
            match = _LETTER_KEY.fullmatch(str(key).strip())
            if match:
                by_letter[match.group(1).upper()] = _option_text(value)
        if all(by_letter.get(letter) for letter in "ABCD"):
            return [by_letter[letter] for letter in "ABCD"]
        # Some models return an unlabeled mapping. Preserve its insertion order
        # only when it has exactly four entries; do not guess for larger maps.
        if len(raw_options) == 4 and not by_letter:
            return [_option_text(value) for value in raw_options.values()]
        return []
    if isinstance(raw_options, list) and len(raw_options) == 4:
        return [_option_text(value) for value in raw_options]
    return []


def _decode_json(output: str) -> Any:
    if not isinstance(output, str) or not output.strip():
        raise ValueError("The generated quiz was empty.")
    candidate = output.strip()
    candidate = re.sub(r"^\s*```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"\s*```\s*$", "", candidate)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as original_error:
        # Recover a JSON array/object surrounded by short model commentary.
        decoder = json.JSONDecoder()
        for index, char in enumerate(candidate):
            if char not in "[{":
                continue
            try:
                payload, _ = decoder.raw_decode(candidate[index:])
                if isinstance(payload, (list, dict)):
                    return payload
            except json.JSONDecodeError:
                continue
        raise ValueError("The generated quiz was not valid JSON.") from original_error


def parse_quiz_output(output: str) -> list[dict[str, Any]]:
    """Validate quiz JSON and return a stable schema for the API."""
    payload = _decode_json(output)
    raw_questions = payload
    if isinstance(payload, dict):
        raw_questions = payload.get("questions", payload.get("quiz"))
    if not isinstance(raw_questions, list) or not 1 <= len(raw_questions) <= 30:
        raise ValueError("The generated quiz did not contain a supported number of questions.")

    parsed: list[dict[str, Any]] = []
    for raw in raw_questions:
        if not isinstance(raw, dict):
            raise ValueError("A generated quiz question was malformed.")
        question_value = raw.get("question", raw.get("question_text", ""))
        question = str(question_value).strip() if question_value is not None else ""
        raw_options = raw.get("options", raw.get("choices", raw.get("answers", {})))
        options = _normalize_options(raw_options)
        if len(options) != 4 or any(not option for option in options):
            raise ValueError("A generated question must contain exactly four non-empty options.")

        correct_raw = raw.get(
            "correct_option",
            raw.get("correct_answer", raw.get("answer", "")),
        )
        correct_text = str(correct_raw).strip()
        match = _ANSWER_PREFIX.match(correct_text.upper())
        if match:
            correct = match.group(1).upper()
        else:
            # Accept an answer matching the displayed option text.
            matches = [i for i, option in enumerate(options) if option.casefold() == correct_text.casefold()]
            correct = "ABCD"[matches[0]] if len(matches) == 1 else correct_text.upper()

        if correct not in {"A", "B", "C", "D"} or not question:
            raise ValueError("A generated question is missing its prompt or correct option.")

        explanation_value = raw.get("explanation", "")
        explanation = str(explanation_value).strip() if explanation_value is not None else ""
        parsed.append({
            "question": question[:4000],
            "options": [option[:1000] for option in options],
            "correct_option": correct,
            "explanation": explanation[:4000],
        })
    return parsed
