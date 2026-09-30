import json

from core.config import Config
from core.memory import MemoryStore
from core.orchestrator import Orchestrator
from core.supervisor import Supervisor


class FakeRouter:
    def __init__(self, responses):
        self.responses = {k: list(v) for k, v in responses.items()}
        self.calls = []
        self.prompts = []

    def ask(self, role, system, prompt):
        self.calls.append(role)
        self.prompts.append((role, prompt, system))
        if role not in self.responses or not self.responses[role]:
            raise RuntimeError(f"out of responses for {role}")
        return self.responses[role].pop(0)


class FakeLogger:
    def __init__(self):
        self.events = []
    def info(self, msg, *a, **k):
        self.events.append((msg, k.get("extra", {})))
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass


def _build(responses, workspace=None, run_id="t"):
    config = Config()
    memory = MemoryStore()
    supervisor = Supervisor(config)
    router = FakeRouter(responses)
    orch = Orchestrator(
        config=config, router=router, memory=memory,
        supervisor=supervisor, logger=FakeLogger(),
        run_id=run_id, workspace=workspace,
    )
    return orch, router


def test_dry_run():
    plan = {"steps": [{"step": 1, "agent": "researcher",
                       "objective": "x", "tool": None, "path": None}]}
    orch, router = _build({"planner": [json.dumps(plan)]})
    result = orch.run("g", dry_run=True)
    assert result["status"] == "DRY_RUN"
    assert router.calls == ["planner"]


def test_dry_run_planner_error_is_structured():
    """Regressão: dry-run com planner falhando devolve JSON, não traceback."""
    orch, _ = _build({"planner": []})
    result = orch.run("g", dry_run=True)
    assert result["status"] == "PLANNER_ERROR"
    assert "reason" in result


def test_planner_validation_error_triggers_replan_with_feedback():
    """Plano inválido (path em write) → feedback e retry, não morte terminal."""
    invalid = {"steps": [{"step": 1, "agent": "coder", "objective": "x",
                          "tool": "filesystem.write", "path": "x.txt"}]}
    valid = {"steps": [{"step": 1, "agent": "researcher", "objective": "x",
                        "tool": None, "path": None}]}
    critique = {"decision": "APPROVE", "score": 0.9,
                "problems": [], "next_action": ""}
    orch, router = _build({
        "planner": [json.dumps(invalid), json.dumps(valid)],
        "researcher": ["out"],
        "critic": [json.dumps(critique)],
    })
    result = orch.run("g")
    assert result["status"] == "COMPLETED"
    assert result["replans"] == 1
    planner_prompts = [p for r, p, _ in router.prompts if r == "planner"]
    assert "rejeitado pelo validador" in planner_prompts[1]


def test_full_flow():
    plan = {"steps": [{"step": 1, "agent": "researcher",
                       "objective": "x", "tool": None, "path": None}]}
    critique = {"decision": "APPROVE", "score": 0.9,
                "problems": [], "next_action": ""}
    orch, router = _build({
        "planner": [json.dumps(plan)],
        "researcher": ["out"],
        "critic": [json.dumps(critique)],
    })
    result = orch.run("g")
    assert result["status"] == "COMPLETED"
    assert router.calls == ["planner", "researcher", "critic"]


def test_low_confidence_escalates_for_human_review(monkeypatch):
    """confidence < DECISION_MIN_CONFIDENCE => ESCALATE, fail-closed."""
    monkeypatch.setenv("DECISION_MIN_CONFIDENCE", "0.9")
    plan = {"steps": [{"step": 1, "agent": "researcher",
                       "objective": "x", "tool": None, "path": None}]}
    critique = {"decision": "APPROVE", "score": 0.9, "problems": [],
                "next_action": "", "confidence": 0.5}
    orch, _ = _build({
        "planner": [json.dumps(plan)],
        "researcher": ["out"],
        "critic": [json.dumps(critique)],
    })
    result = orch.run("g")
    assert result["status"] == "ESCALATED"
    assert result["results"][-1]["status"] == "ESCALATED"
    assert "revisão humana" in result["reason"].lower()


def test_confidence_at_threshold_does_not_escalate(monkeypatch):
    monkeypatch.setenv("DECISION_MIN_CONFIDENCE", "0.5")
    plan = {"steps": [{"step": 1, "agent": "researcher",
                       "objective": "x", "tool": None, "path": None}]}
    critique = {"decision": "APPROVE", "score": 0.9, "problems": [],
                "next_action": "", "confidence": 0.5}
    orch, _ = _build({
        "planner": [json.dumps(plan)],
        "researcher": ["out"],
        "critic": [json.dumps(critique)],
    })
    result = orch.run("g")
    assert result["status"] == "COMPLETED"


def test_critic_decision_escalate_direct(monkeypatch):
    """Engine tipado pode emitir ESCALATE direto — run para, sem replan."""
    monkeypatch.delenv("DECISION_MIN_CONFIDENCE", raising=False)
    plan = {"steps": [{"step": 1, "agent": "researcher",
                       "objective": "x", "tool": None, "path": None}]}
    critique = {"decision": "ESCALATE", "score": 0.5, "problems": ["duvida"],
                "next_action": "revisar", "confidence": 0.3}
    orch, router = _build({
        "planner": [json.dumps(plan)],
        "researcher": ["out"],
        "critic": [json.dumps(critique)],
    })
    result = orch.run("g")
    assert result["status"] == "ESCALATED"
    # fail-closed: não tenta replan nem continua o plano
    assert router.calls == ["planner", "researcher", "critic"]


def test_rules_engine_full_flow(monkeypatch):
    """DECISION_ENGINE=rules: critic determinístico, offline, sem chamada LLM."""
    monkeypatch.setenv("DECISION_ENGINE", "rules")
    plan = {"steps": [{"step": 1, "agent": "researcher",
                       "objective": "x", "tool": None, "path": None}]}
    orch, router = _build({
        "planner": [json.dumps(plan)],
        "researcher": ["out limpo e completo"],
    })
    result = orch.run("g")
    assert result["status"] == "COMPLETED"
    assert "critic" not in router.calls  # nenhum LLM chamado para decidir



def test_read_content_reaches_agent(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.txt").write_text("SENTINELA_XYZ", encoding="utf-8")

    plan = {"steps": [{"step": 1, "agent": "researcher",
                       "objective": "resumir",
                       "tool": "filesystem.read", "path": "notes.txt"}]}
    critique = {"decision": "APPROVE", "score": 0.9,
                "problems": [], "next_action": ""}
    orch, router = _build(
        {"planner": [json.dumps(plan)],
         "researcher": ["resumo"],
         "critic": [json.dumps(critique)]},
        workspace=workspace,
    )
    result = orch.run("g")
    assert result["status"] == "COMPLETED"

    researcher_prompt = next(p for r, p, _ in router.prompts if r == "researcher")
    assert "SENTINELA_XYZ" in researcher_prompt


def test_read_missing_file_produces_feedback():
    plan = {"steps": [{"step": 1, "agent": "researcher",
                       "objective": "resumir",
                       "tool": "filesystem.read", "path": "nope.txt"}]}
    orch, _ = _build({"planner": [json.dumps(plan)] * 5})
    result = orch.run("g")
    assert result["status"] == "REPLAN_LIMIT"
    assert result["results"][0]["status"] == "ERROR"


def test_replan_limit():
    bad = {"steps": [{"step": 1, "agent": "researcher",
                      "objective": "x", "tool": None, "path": None}]}
    rej = {"decision": "REJECT", "score": 0.1,
           "problems": ["p"], "next_action": "n"}
    orch, _ = _build({
        "planner": [json.dumps(bad)] * 6,
        "researcher": ["o"] * 6,
        "critic": [json.dumps(rej)] * 6,
    })
    result = orch.run("g")
    assert result["status"] == "REPLAN_LIMIT"
    assert result["replans"] >= 1


def test_sandbox_output_reaches_agent(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOW_SANDBOX", "true")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "gen.py").write_text("print('SAIDAS_777')", encoding="utf-8")

    plan = {"steps": [{"step": 1, "agent": "researcher",
                       "objective": "analisar",
                       "tool": "sandbox.execute", "path": "gen.py"}]}
    critique = {"decision": "APPROVE", "score": 0.9,
                "problems": [], "next_action": ""}
    orch, router = _build(
        {"planner": [json.dumps(plan)],
         "researcher": ["ok"],
         "critic": [json.dumps(critique)]},
        workspace=workspace,
    )
    result = orch.run("g")
    assert result["status"] == "COMPLETED"

    researcher_prompt = next(p for r, p, _ in router.prompts if r == "researcher")
    assert "SAIDAS_777" in researcher_prompt


def test_sandbox_disabled_produces_feedback(tmp_path, monkeypatch):
    """ALLOW_SANDBOX ausente → step falha com feedback e vai para replan."""
    monkeypatch.delenv("ALLOW_SANDBOX", raising=False)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "gen.py").write_text("print('x')", encoding="utf-8")

    plan = {"steps": [{"step": 1, "agent": "researcher",
                       "objective": "analisar",
                       "tool": "sandbox.execute", "path": "gen.py"}]}
    orch, _ = _build({"planner": [json.dumps(plan)] * 5}, workspace=workspace)
    result = orch.run("g")
    assert result["status"] == "REPLAN_LIMIT"
    assert result["results"][0]["status"] == "ERROR"


_Critique = json.dumps({"decision": "APPROVE", "score": 0.9,
                        "problems": [], "next_action": ""})


def test_answer_field_is_the_researcher_text():
    """A resposta final do run sai no payload, não só na memória."""
    plan = {"steps": [{"step": 1, "agent": "researcher",
                       "objective": "resumir", "tool": None, "path": None}]}
    orch, _ = _build({
        "planner": [json.dumps(plan)],
        "researcher": ["A media de [4, 7, 10] e 7.0"],
        "critic": [_Critique],
    })
    result = orch.run("g")
    assert result["status"] == "COMPLETED"
    assert result["answer"] == "A media de [4, 7, 10] e 7.0"


def test_coder_without_write_tool_informs_model_and_logs(tmp_path):
    """Regressão: coder sob step SEM filesystem.write — a proposta não é
    gravada. O modelo precisa ser avisado (senão alega criar arquivos) e
    o descarte precisa aparecer no log (antes era silencioso)."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    plan = {"steps": [{"step": 1, "agent": "coder",
                       "objective": "resumir saida",
                       "tool": None, "path": None}]}
    proposal = json.dumps({
        "summary": "resumo da execucao",
        "files": [{"path": "resumo.md", "content": "# Resumo\n"}],
    })
    orch, router = _build({
        "planner": [json.dumps(plan)],
        "coder": [proposal],
        "critic": [_Critique],
    }, workspace=workspace)
    result = orch.run("g")

    assert result["status"] == "COMPLETED"
    assert result["answer"] == "resumo da execucao"

    # modelo foi avisado de que nada será gravado
    coder_prompts = [p for r, p, _ in router.prompts if r == "coder"]
    assert coder_prompts and "NÃO serão gravados" in coder_prompts[0]

    # descarte visível no log
    drops = [extra for msg, extra in orch.logger.events
             if msg == "proposal_not_written"]
    assert drops and drops[0]["files"] == 1

    # e nada foi gravado mesmo (design: escrita opt-in do planner)
    assert not (workspace / "resumo.md").exists()


def test_coder_with_write_tool_writes_without_warning(tmp_path):
    """Com filesystem.write no step, a proposta é gravada e não há
    proposal_not_written."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    plan = {"steps": [{"step": 1, "agent": "coder",
                       "objective": "criar resumo",
                       "tool": "filesystem.write", "path": None}]}
    proposal = json.dumps({
        "summary": "arquivo criado",
        "files": [{"path": "resumo.md", "content": "# Resumo\n"}],
    })
    orch, _ = _build({
        "planner": [json.dumps(plan)],
        "coder": [proposal],
        "critic": [_Critique],
    }, workspace=workspace)
    result = orch.run("g")

    assert result["status"] == "COMPLETED"
    assert result["answer"] == "arquivo criado"
    assert (workspace / "resumo.md").read_text(encoding="utf-8") == "# Resumo\n"
    assert not any(msg == "proposal_not_written"
                   for msg, _ in orch.logger.events)


def test_approve_sem_confidence_escalate_com_limiar_explicito(monkeypatch):
    """Regressão de segurança (fail-closed): APPROVE com confidence AUSENTE
    e limiar explícito > 0 não pode passar — o limiar exige o número."""
    monkeypatch.setenv("DECISION_MIN_CONFIDENCE", "0.5")
    plan = {"steps": [{"step": 1, "agent": "researcher",
                       "objective": "x", "tool": None, "path": None}]}
    critique = {"decision": "APPROVE", "score": 0.9,
                "problems": [], "next_action": ""}  # sem confidence
    orch, _ = _build({
        "planner": [json.dumps(plan)],
        "researcher": ["out"],
        "critic": [json.dumps(critique)],
    })
    result = orch.run("g")
    assert result["status"] == "ESCALATED"
    assert "confidence ausente" in str(result["results"][-1])
