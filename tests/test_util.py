import pytest

from core.util import parse_json_llm, tail_truncate, truncate


def test_plain_json():
    assert parse_json_llm('{"a": 1}')["a"] == 1


def test_json_fence():
    assert parse_json_llm('```json\n{"a": 2}\n```')["a"] == 2


def test_json_with_prose():
    assert parse_json_llm('blah\n{"a": 3}\nblah')["a"] == 3


def test_think_block():
    assert parse_json_llm("\n{\"a\": 4}")["a"] == 4


def test_nested_json_does_not_get_cut():
    """Regression: non-greedy regex used to cut at first closing brace."""
    result = parse_json_llm('{"steps": [{"agent": "x", "tool": null}]}')
    assert result["steps"][0]["agent"] == "x"


def test_literal_newline_inside_string():
    """Regressão: LLM emite newline REAL dentro de string (não \\n escapado).

    Causa raiz de 'JSON inválido' intermitente no coder — strict=False
    aceita o controle sem afrouxar a sintaxe do JSON.
    """
    raw = '{\n  "summary": "linha1\nlinha2",\n  "files": []\n}'
    result = parse_json_llm(raw)
    assert result["summary"] == "linha1\nlinha2"


def test_literal_newline_in_deeply_nested_content():
    """Caso real: content de arquivo markdown multi-linha dentro do JSON."""
    raw = (
        '{"summary": "ok", "files": [{"path": "r.md", "content":'
        ' "# Titulo\n\ntexto com \\t tab\\n"}]}'
    )
    result = parse_json_llm(raw)
    assert result["files"][0]["content"].startswith("# Titulo")


def test_strict_false_does_not_accept_broken_syntax():
    """strict=False aceita controle em string, NÃO afrouxar sintaxe."""
    with pytest.raises(ValueError):
        parse_json_llm('{"summary": "sem fechamento')
    with pytest.raises(ValueError):
        parse_json_llm('{"a": 1,}')  # vírgula trailing continua inválida


def test_truncate_keeps_head():
    assert truncate("abcdefghij", 5).startswith("abcde")


def test_tail_truncate_keeps_tail():
    assert tail_truncate("abcdefghij", 5).endswith("fghij")
