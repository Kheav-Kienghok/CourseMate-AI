from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import requests

from utils.config import get_gemini_api_key, get_gemini_model

logger = logging.getLogger(__name__)


SUPPORTED_INTENTS: set[str] = {
    "today_assignments",
    "course_assignments",
    "grades",
    "overall_performance",
    "grade_calculation",
    "unknown",
}


LETTER_GRADES: set[str] = {
    "A",
    "A-",
    "B+",
    "B",
    "B-",
    "C+",
    "C",
    "C-",
    "D+",
    "D",
    "D-",
    "F",
}


CALCULATION_TYPES: set[str] = {
    "current_total",
    "required_score",
}


@dataclass(frozen=True)
class ParsedIntent:
    intent: str
    course: str | None = None
    date: str | None = None
    grade_inputs: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    error: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


def unknown_intent(error: str | None = None) -> ParsedIntent:
    return ParsedIntent(intent="unknown", confidence=0.0, error=error)


def parse_user_intent(
    message_text: str,
    *,
    today: date,
    available_courses: list[str] | None = None,
) -> ParsedIntent:
    """Parse free-text user message into a validated intent payload.

    Uses Gemini Flash with JSON-only response mode, validates output shape,
    and falls back to an "unknown" intent if anything is invalid.
    """

    text = message_text.strip()
    if not text:
        return unknown_intent("Empty message")

    api_key = get_gemini_api_key()
    if not api_key:
        return unknown_intent("GEMINI_API_KEY is not configured")

    model = get_gemini_model()

    prompt = _build_prompt(
        message_text=text,
        today=today,
        available_courses=available_courses or [],
    )

    last_error: str | None = None

    # First try with response schema. If a model/version rejects schema fields,
    # we retry with JSON mime type only.
    for include_schema in (True, False):
        try:
            raw = _generate_json_response(
                api_key=api_key,
                model=model,
                prompt=prompt,
                include_schema=include_schema,
            )
            payload = _decode_json_payload(raw)
            return _validate_payload(payload, today=today)
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            logger.warning(
                "Gemini intent parsing failed (schema=%s): %s",
                include_schema,
                exc,
            )

    return unknown_intent(last_error or "Unable to parse intent")


def _build_prompt(
    *,
    message_text: str,
    today: date,
    available_courses: list[str],
) -> str:
    courses_block = "\n".join(f"- {name}" for name in available_courses[:30])
    if not courses_block:
        courses_block = "- (no courses provided)"

    today_iso = today.isoformat()

    return (
        "You are an intent parser for a Canvas Telegram assistant.\n"
        "Return only one JSON object and nothing else.\n"
        "Do not wrap JSON in markdown code fences.\n"
        "\n"
        "Allowed intents:\n"
        "- today_assignments\n"
        "- course_assignments\n"
        "- grades\n"
        "- overall_performance\n"
        "- grade_calculation\n"
        "- unknown\n"
        "\n"
        "Output schema (JSON object):\n"
        "{\n"
        '  "intent": "...",\n'
        '  "course": "string or null",\n'
        '  "date": "YYYY-MM-DD or null",\n'
        "  \"grade_inputs\": {\n"
        '    "calculation_type": "current_total|required_score|null",\n'
        '    "target_percent": "number or null",\n'
        '    "current_percent": "number or null",\n'
        '    "final_weight_percent": "number or null",\n'
        '    "current_weight_percent": "number or null",\n'
        '    "desired_letter": "A/A-/.../F or null",\n'
        '    "components": [\n'
        "      {\n"
        '        "name": "component name (midterm/final/assignment)",\n'
        '        "score": "number 0..100 or null",\n'
        '        "weight_percent": "number 0..100",\n'
        '        "is_target_component": "boolean or null"\n'
        "      }\n"
        "    ]\n"
        "  },\n"
        '  "confidence": "0..1"\n'
        "}\n"
        "\n"
        f"Today is {today_iso}. Resolve relative dates accordingly.\n"
        "\n"
        "Available courses (for course name matching):\n"
        f"{courses_block}\n"
        "\n"
        "Examples:\n"
        "User: what assignments are due today?\n"
        "JSON: {\"intent\":\"today_assignments\",\"course\":null,\"date\":\""
        + today_iso
        + "\",\"grade_inputs\":{\"target_percent\":null,\"current_percent\":null,\"final_weight_percent\":null,\"current_weight_percent\":null,\"desired_letter\":null},\"confidence\":0.96}\n"
        "\n"
        "User: show me assignments for database systems\n"
        "JSON: {\"intent\":\"course_assignments\",\"course\":\"database systems\",\"date\":null,\"grade_inputs\":{\"target_percent\":null,\"current_percent\":null,\"final_weight_percent\":null,\"current_weight_percent\":null,\"desired_letter\":null},\"confidence\":0.92}\n"
        "\n"
        "User: if I have 78 now and final is 40 percent, what do I need to get an A-?\n"
        "JSON: {\"intent\":\"grade_calculation\",\"course\":null,\"date\":null,\"grade_inputs\":{\"calculation_type\":\"required_score\",\"target_percent\":null,\"current_percent\":78,\"final_weight_percent\":40,\"current_weight_percent\":60,\"desired_letter\":\"A-\",\"components\":[]},\"confidence\":0.9}\n"
        "\n"
        "User: midterm 30% i got 80, assignments 30% i got 70, final 40% what do i need for A?\n"
        "JSON: {\"intent\":\"grade_calculation\",\"course\":null,\"date\":null,\"grade_inputs\":{\"calculation_type\":\"required_score\",\"target_percent\":null,\"current_percent\":null,\"final_weight_percent\":null,\"current_weight_percent\":null,\"desired_letter\":\"A\",\"components\":[{\"name\":\"midterm\",\"score\":80,\"weight_percent\":30,\"is_target_component\":false},{\"name\":\"assignments\",\"score\":70,\"weight_percent\":30,\"is_target_component\":false},{\"name\":\"final\",\"score\":null,\"weight_percent\":40,\"is_target_component\":true}]},\"confidence\":0.91}\n"
        "\n"
        "User: my midterm is 78 with 40 percent and assignment is 90 with 60 percent, what's my current total?\n"
        "JSON: {\"intent\":\"grade_calculation\",\"course\":null,\"date\":null,\"grade_inputs\":{\"calculation_type\":\"current_total\",\"target_percent\":null,\"current_percent\":null,\"final_weight_percent\":null,\"current_weight_percent\":null,\"desired_letter\":null,\"components\":[{\"name\":\"midterm\",\"score\":78,\"weight_percent\":40,\"is_target_component\":null},{\"name\":\"assignment\",\"score\":90,\"weight_percent\":60,\"is_target_component\":null}]},\"confidence\":0.9}\n"
        "\n"
        "User message:\n"
        f"{message_text}"
    )


def _generate_json_response(
    *,
    api_key: str,
    model: str,
    prompt: str,
    include_schema: bool,
) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    generation_config: dict[str, Any] = {
        "temperature": 0,
        "responseMimeType": "application/json",
    }

    if include_schema:
        generation_config["responseSchema"] = _response_schema()

    payload: dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": prompt,
                    }
                ],
            }
        ],
        "generationConfig": generation_config,
    }

    response = requests.post(
        url,
        params={"key": api_key},
        json=payload,
        timeout=20,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Gemini API error {response.status_code}: {response.text[:400]}"
        )

    data = response.json()

    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise RuntimeError("Gemini response did not contain candidates")

    first = candidates[0]
    content = first.get("content") if isinstance(first, dict) else None
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list) or not parts:
        raise RuntimeError("Gemini response candidate did not contain content parts")

    for part in parts:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if isinstance(text, str) and text.strip():
            return text

    raise RuntimeError("Gemini response did not contain textual JSON output")


def _decode_json_payload(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\\n", "", text)
        text = text.removesuffix("```").strip()

    # Defensive extraction if model still returns extra prose around JSON.
    if not text.startswith("{"):
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError("Model output did not contain a JSON object")
        text = match.group(0)

    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("Model output JSON must be an object")
    return payload


def _validate_payload(payload: dict[str, Any], *, today: date) -> ParsedIntent:
    raw_intent = payload.get("intent")
    intent = str(raw_intent).strip().lower() if raw_intent is not None else "unknown"

    if intent not in SUPPORTED_INTENTS:
        intent = "unknown"

    raw_course = payload.get("course")
    course = str(raw_course).strip() if isinstance(raw_course, str) else None
    if course == "":
        course = None

    raw_date = payload.get("date")
    normalized_date = _normalize_date(raw_date, today=today)

    grade_inputs_raw = payload.get("grade_inputs")
    grade_inputs = _normalize_grade_inputs(grade_inputs_raw)

    confidence = _to_float(payload.get("confidence"), minimum=0.0, maximum=1.0)
    confidence = confidence if confidence is not None else 0.0

    return ParsedIntent(
        intent=intent,
        course=course,
        date=normalized_date,
        grade_inputs=grade_inputs,
        confidence=confidence,
        raw_payload=payload,
    )


def _normalize_date(value: Any, *, today: date) -> str | None:
    if value is None:
        return None

    raw = str(value).strip().lower()
    if not raw:
        return None

    if raw == "today":
        return today.isoformat()
    if raw == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    if raw == "yesterday":
        return (today - timedelta(days=1)).isoformat()

    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        return None

    return parsed.isoformat()


def _normalize_grade_inputs(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}

    calculation_type_raw = source.get("calculation_type")
    calculation_type = (
        str(calculation_type_raw).strip().lower()
        if isinstance(calculation_type_raw, str)
        else None
    )
    if calculation_type not in CALCULATION_TYPES:
        calculation_type = None

    desired_letter_raw = source.get("desired_letter")
    desired_letter = (
        str(desired_letter_raw).strip().upper()
        if isinstance(desired_letter_raw, str)
        else None
    )
    if desired_letter not in LETTER_GRADES:
        desired_letter = None

    normalized_components: list[dict[str, Any]] = []
    raw_components = source.get("components")
    if isinstance(raw_components, list):
        for idx, item in enumerate(raw_components):
            if not isinstance(item, dict):
                continue

            name_raw = item.get("name")
            if isinstance(name_raw, str):
                name = name_raw.strip()
            elif name_raw is None:
                name = ""
            else:
                name = str(name_raw).strip()

            if not name:
                name = f"component_{idx + 1}"

            score = _to_float(item.get("score"), minimum=0.0, maximum=100.0)
            weight_percent = _to_float(
                item.get("weight_percent"),
                minimum=0.0,
                maximum=100.0,
            )
            is_target_component = _to_bool(item.get("is_target_component"))

            normalized_components.append(
                {
                    "name": name,
                    "score": score,
                    "weight_percent": weight_percent,
                    "is_target_component": is_target_component,
                }
            )

    return {
        "calculation_type": calculation_type,
        "target_percent": _to_float(source.get("target_percent"), minimum=0.0, maximum=100.0),
        "current_percent": _to_float(source.get("current_percent"), minimum=0.0, maximum=100.0),
        "final_weight_percent": _to_float(
            source.get("final_weight_percent"),
            minimum=0.0,
            maximum=100.0,
        ),
        "current_weight_percent": _to_float(
            source.get("current_weight_percent"),
            minimum=0.0,
            maximum=100.0,
        ),
        "desired_letter": desired_letter,
        "components": normalized_components,
    }


def _to_float(
    value: Any,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    if value is None:
        return None

    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None

    if minimum is not None and converted < minimum:
        return None
    if maximum is not None and converted > maximum:
        return None

    return converted


def _to_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
        return None

    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "y", "1"}:
            return True
        if lowered in {"false", "no", "n", "0"}:
            return False

    return None


def _response_schema() -> dict[str, Any]:
    return {
        "type": "OBJECT",
        "required": ["intent", "course", "date", "grade_inputs", "confidence"],
        "properties": {
            "intent": {
                "type": "STRING",
                "enum": sorted(SUPPORTED_INTENTS),
            },
            "course": {"type": "STRING"},
            "date": {"type": "STRING"},
            "grade_inputs": {
                "type": "OBJECT",
                "properties": {
                    "calculation_type": {
                        "type": "STRING",
                        "enum": sorted(CALCULATION_TYPES),
                    },
                    "target_percent": {"type": "NUMBER"},
                    "current_percent": {"type": "NUMBER"},
                    "final_weight_percent": {"type": "NUMBER"},
                    "current_weight_percent": {"type": "NUMBER"},
                    "desired_letter": {
                        "type": "STRING",
                        "enum": sorted(LETTER_GRADES),
                    },
                    "components": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "name": {"type": "STRING"},
                                "score": {"type": "NUMBER"},
                                "weight_percent": {"type": "NUMBER"},
                                "is_target_component": {"type": "BOOLEAN"},
                            },
                        },
                    },
                },
            },
            "confidence": {"type": "NUMBER"},
        },
    }
