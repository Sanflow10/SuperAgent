import json

import pytest
from pydantic import ValidationError

from agents.coder import CodeProposal, Coder


class FakeRouter:
    """Devolve uma sequência de respostas; levanta se acabar."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def ask(self, role, system, prompt):
        self.calls += 1
        if not self.responses:
            raise RuntimeError("sem respostas restantes")
        return self.responses.pop(0)


VALID = json.dumps({
    "summary": "ok",
    "files": [{"path": "a.py", "content": "print(1)"}],
})


def test_coder_valid_first_try_no_retry():
    router = FakeRouter([VALID])
    proposal = Coder(router, None, None).run("g", "o", "")
    assert isinstance(proposal, CodeProposal)
    assert router.calls == 1
    assert proposal.files[0].path == "a.py"


def test_coder_retries_once_on_malformed_json():
    """Glitch intermitente do backend: primeira resposta lixo, segunda boa."""
    router = FakeRouter(["isso nao e json", VALID])
    proposal = Coder(router, None, None).run("g", "o", "")
    assert proposal.summary == "ok"
    assert router.calls == 2


def test_coder_retries_on_valid_json_but_wrong_schema():
    """JSON válido mas sem os campos obrigatórios também dispara retry."""
    wrong = json.dumps({"summary": "falta files"})
    router = FakeRouter([wrong, VALID])
    proposal = Coder(router, None, None).run("g", "o", "")
    assert router.calls == 2
    assert len(proposal.files) == 1


def test_coder_persistent_failure_raises_with_raw_snippet():
    """Falha persistente → erro único com a resposta crua diagnosticável."""
    garbage = "resposta inteiramente invalida sem chaves"
    router = FakeRouter([garbage, garbage])
    with pytest.raises(ValueError, match="2 tentativas") as excinfo:
        Coder(router, None, None).run("g", "o", "")
    assert router.calls == 2
    assert garbage in str(excinfo.value)  # snippet cru presente no erro


def test_coder_does_not_retry_when_router_itself_fails():
    """Erro de rede/timeout não é problema de formato — não repete o call."""

    class DownRouter:
        calls = 0

        def ask(self, role, system, prompt):
            self.calls += 1
            raise RuntimeError("Ollama indisponível após 3 tentativas")

    router = DownRouter()
    with pytest.raises(RuntimeError, match="indisponível"):
        Coder(router, None, None).run("g", "o", "")
    assert router.calls == 1


def test_codeproposal_score_bounds_really_validate():
    """Sanidade: o schema continua estrito (não regressão)."""
    with pytest.raises(ValidationError):
        CodeProposal.model_validate({"summary": "", "files": "nao-e-lista"})
