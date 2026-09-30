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


def test_naked_json_with_inner_code_fence():
    """Regressão: JSON válido cujo content markdown contém ``` — o FENCE_RE
    casava o fence DE DENTRO da string e destruía o JSON antes do parse.
    Era a causa das falhas 'JSON inválido' do coder com propostas reais."""
    raw = (
        '{"summary": "ok", "files": [{"path": "r.md", "content":'
        ' "# Titulo\\n\\n```\\nA media de [4, 7, 10] e 7.0\\n```\\n"}]}'
    )
    result = parse_json_llm(raw)
    assert "```" in result["files"][0]["content"]


def test_wrapped_fence_still_works():
    """JSON embrulhado em ```json com prosa continua sendo extraído."""
    raw = 'Claro! Aqui esta:\n```json\n{"a": 5}\n```\nPronto.'
    assert parse_json_llm(raw)["a"] == 5


def test_prose_with_braces_before_fence():
    """Prosa com chave solta ANTES do fence: o fence ainda vence."""
    raw = 'Use {"a": 1} como exemplo. Resposta:\n```json\n{"b": 2}\n```'
    assert parse_json_llm(raw)["b"] == 2


def test_real_unparseable_response_from_run():
    """Resposta REAL gravada em logs/coder_unparseable.log (run
    6c49b0e8) que falhava com o parser antigo — precisa parsear."""
    raw = (
        '{\n  "summary": "Execucao registrada",\n  "files": [\n    {\n'
        '      "path": "resumo.md",\n      "content": "# Resumo\\n\\n'
        '```\\nA media de [4, 7, 10] e 7.0\\n```\\n"\n    }\n  ]\n}'
    )
    result = parse_json_llm(raw)
    assert result["files"][0]["path"] == "resumo.md"


def test_truncate_keeps_head():
    assert truncate("abcdefghij", 5).startswith("abcde")


def test_tail_truncate_keeps_tail():
    assert tail_truncate("abcdefghij", 5).endswith("fghij")
