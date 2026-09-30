import json
import re
from typing import Any


FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)
THINK_RE = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.IGNORECASE | re.DOTALL)


def clean_llm_text(raw: str) -> str:
    """Parser hygiene — not a security boundary."""

    if not isinstance(raw, str):
        raise TypeError("LLM response must be str")

    text = THINK_RE.sub("", raw).strip()

    if text and text[0] not in "{[":
        for index, char in enumerate(text):
            if char in "{[":
                text = text[index:]
                break

    return text


def parse_json_llm(raw: str) -> Any:
    """
    Robust JSON parser for LLM responses.

    Handles fences,  FreeBSD thought blocks, surrounding prose, and nested JSON
    (relies on rfind('}') fallback instead of non-greedy regex).
    """

    text = clean_llm_text(raw)

    match = FENCE_RE.search(text)
    if match:
        text = match.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError("Não foi possível extrair JSON válido da resposta do modelo.")


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[TRUNCATED]"


def tail_truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return "[...TRUNCATED...]\n\n" + text[-limit:]
