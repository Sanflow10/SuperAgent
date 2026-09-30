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

    Ordem: texto inteiro -> dentro de fence -> faixas { ... }.

    A ordem importa: uma resposta que JÁ é JSON válido precisa ser aceita
    como está. Extrair o fence PRIMEIRO destruía JSON cujas strings contêm
    fences markdown (ex.: content de arquivo com bloco de código) — o
    FENCE_RE casava o fence de dentro e descartava o JSON inteiro.

    Usa strict=False: LLMs frequentemente emitem newline/controle LITERAL
    dentro de strings (em vez de \\n escapado) — a sintaxe continua sendo a
    do JSON, só os controles dentro de string são aceitos.
    """

    text = clean_llm_text(raw)

    # 1) O texto inteiro já é JSON (caso mais comum; cobre JSON que
    #    contém fences/newlines dentro das strings).
    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError:
        pass

    # 2) Resposta embrulhada em ```json ... ``` (com prosa em volta).
    match = FENCE_RE.search(text)
    if match:
        try:
            return json.loads(match.group(1).strip(), strict=False)
        except json.JSONDecodeError:
            pass

    # 3) Prosa com chaves: recorta do primeiro { ao último }.
    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1], strict=False)
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
