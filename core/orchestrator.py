import json
import time

from agents.coder import Coder
from agents.critic import Critic
from agents.planner import Planner
from agents.researcher import Researcher
from core.config import Config
from core.decisions import build_engine
from core.util import tail_truncate, truncate
from tools.registry import ToolRegistry


class Orchestrator:

    def __init__(
        self,
        config: Config,
        router,
        memory,
        supervisor,
        logger,
        run_id: str,
        workspace=None,
    ):
        self.config = config
        self.router = router
        self.memory = memory
        self.supervisor = supervisor
        self.logger = logger
        self.run_id = run_id

        self.tools = ToolRegistry(config, workspace=workspace)

        self.max_context = config.env_int(
            "MAX_CONTEXT_CHARS", "limits", "max_context_chars", default=24000
        )
        self.max_read_chars = config.env_int(
            "MAX_READ_CHARS", "limits", "max_read_chars", default=8000
        )

        self.planner = Planner(router, memory, logger)
        self.researcher = Researcher(router, memory, logger)
        self.coder = Coder(router, memory, logger)

        engine = build_engine(config, router)
        self.min_confidence = config.env_float(
            "DECISION_MIN_CONFIDENCE", "decision", "min_confidence", default=0.0
        )
        self.critic = Critic(router, memory, logger, engine=engine)
        self._log(
            "decision_engine_selected",
            engine=engine.name,
            min_confidence=self.min_confidence,
        )

    def _log(self, event: str, **fields):
        self.logger.info(event, extra={"event": event, "run_id": self.run_id, **fields})

    def context(self) -> str:
        records = self.memory.recent(limit=20, run_id=self.run_id)
        text = "\n".join(
            f"[{record['kind']}] {record['content']}"
            for record in reversed(records)
        )
        return tail_truncate(text, self.max_context)

    def execute_tool(self, tool: str, arguments: dict):
        ok, reason = self.supervisor.authorize_tool(tool)
        if not ok:
            raise PermissionError(reason)
        return self.tools.execute(tool, arguments)

    def run(self, goal: str, dry_run: bool = False):
        ok, reason = self.supervisor.check_goal(goal)
        if not ok:
            return {"run_id": self.run_id, "status": "BLOCKED", "reason": reason}

        if dry_run:
            started = time.monotonic()
            try:
                plan = self.planner.run(goal=goal, context="", feedback="")
            except Exception as exc:  # noqa: BLE001
                self._log("planner_error", error=str(exc))
                return {
                    "run_id": self.run_id,
                    "status": "PLANNER_ERROR",
                    "reason": str(exc),
                    "plan": None,
                    "results": [],
                }
            self._log(
                "dry_run_plan",
                elapsed_s=round(time.monotonic() - started, 2),
                steps=len(plan.steps),
            )
            return {
                "run_id": self.run_id,
                "status": "DRY_RUN",
                "plan": plan.model_dump(),
                "results": [],
                "note": "Dry run: nothing persisted.",
            }

        self.memory.add(self.run_id, "goal", goal)

        feedback = ""
        results: list[dict] = []
        last_answer = ""

        while True:
            context = self.context()
            self._log("planning")
            started = time.monotonic()

            try:
                plan = self.planner.run(goal=goal, context=context, feedback=feedback)
            except Exception as exc:  # noqa: BLE001
                self._log("planner_error", error=str(exc))
                results.append(
                    {"step": 0, "status": "PLANNER_ERROR", "reason": str(exc)}
                )
                ok, replan_reason = self.supervisor.authorize_replan()
                if not ok:
                    return {
                        "run_id": self.run_id,
                        "status": "PLANNER_ERROR",
                        "reason": str(exc),
                        "results": results,
                        "answer": last_answer,
                        "replans": self.supervisor.replans,
                        "last_failure": replan_reason,
                    }
                feedback = (
                    f"Seu plano anterior foi rejeitado pelo validador: {exc}. "
                    f"Corrija a violação e responda somente JSON válido. "
                    f"Lembrete: 'path' só existe em filesystem.read e "
                    f"sandbox.execute; em filesystem.write use 'path': null "
                    f"(o caminho vai dentro dos arquivos da proposta)."
                )
                continue

            self._log(
                "planner_done",
                elapsed_s=round(time.monotonic() - started, 2),
                steps=len(plan.steps),
            )

            plan_failed = False
            failure_reason = ""

            for plan_step in plan.steps:
                ok, reason = self.supervisor.check_objective(plan_step.objective)
                if not ok:
                    results.append(
                        {"step": plan_step.step, "status": "BLOCKED", "reason": reason}
                    )
                    plan_failed = True
                    failure_reason = reason
                    feedback = f"Step {plan_step.step} blocked: {reason}"
                    break

                ok, reason = self.supervisor.authorize(
                    plan_step.objective, depth=0, tool=plan_step.tool
                )
                if not ok:
                    results.append(
                        {"step": plan_step.step, "status": "BLOCKED", "reason": reason}
                    )
                    plan_failed = True
                    failure_reason = reason
                    feedback = f"Step {plan_step.step} blocked: {reason}"
                    break

                extra_context = ""
                if plan_step.tool == "filesystem.read":
                    if not plan_step.path:
                        failure_reason = "filesystem.read sem 'path'."
                        feedback = (
                            f"Step {plan_step.step} failed: {failure_reason} "
                            f"Choose a different step."
                        )
                        results.append(
                            {
                                "step": plan_step.step,
                                "status": "ERROR",
                                "reason": failure_reason,
                            }
                        )
                        plan_failed = True
                        break

                    try:
                        file_content = self.execute_tool(
                            "filesystem.read", {"path": plan_step.path}
                        )
                    except Exception as exc:  # noqa: BLE001
                        failure_reason = str(exc)
                        feedback = (
                            f"Step {plan_step.step} failed to read "
                            f"'{plan_step.path}': {failure_reason}\n"
                            f"Do not retry the same path. "
                            f"Pick another file or proceed without reading."
                        )
                        self._log(
                            "read_error",
                            step=plan_step.step,
                            path=plan_step.path,
                            error=failure_reason,
                        )
                        results.append(
                            {
                                "step": plan_step.step,
                                "status": "ERROR",
                                "reason": failure_reason,
                            }
                        )
                        plan_failed = True
                        break

                    safe_content = file_content.replace("</file>", "<\\/file>")
                    extra_context = (
                        f'\n<file path="{plan_step.path}">\n'
                        f"{truncate(safe_content, self.max_read_chars)}\n"
                        f"</file>\n"
                    )
                    self.memory.add(
                        self.run_id,
                        f"step_{plan_step.step}_file_read",
                        f"{plan_step.path} ({len(file_content)} chars)",
                    )

                elif plan_step.tool == "sandbox.execute":
                    if not plan_step.path:
                        failure_reason = "sandbox.execute sem 'path'."
                        feedback = (
                            f"Step {plan_step.step} failed: {failure_reason} "
                            f"Choose a different step."
                        )
                        results.append(
                            {
                                "step": plan_step.step,
                                "status": "ERROR",
                                "reason": failure_reason,
                            }
                        )
                        plan_failed = True
                        break

                    try:
                        sandbox_output = self.execute_tool(
                            "sandbox.execute", {"path": plan_step.path}
                        )
                    except Exception as exc:  # noqa: BLE001
                        failure_reason = str(exc)
                        feedback = (
                            f"Step {plan_step.step} failed to execute "
                            f"'{plan_step.path}': {failure_reason}\n"
                            f"Do not retry the same path. "
                            f"Write a different script or proceed without it."
                        )
                        self._log(
                            "sandbox_error",
                            step=plan_step.step,
                            path=plan_step.path,
                            error=failure_reason,
                        )
                        results.append(
                            {
                                "step": plan_step.step,
                                "status": "ERROR",
                                "reason": failure_reason,
                            }
                        )
                        plan_failed = True
                        break

                    extra_context = (
                        f'\n<sandbox_output path="{plan_step.path}">\n'
                        f"{truncate(sandbox_output, self.max_read_chars)}\n"
                        f"</sandbox_output>\n"
                    )
                    self.memory.add(
                        self.run_id,
                        f"step_{plan_step.step}_sandbox",
                        truncate(sandbox_output, 4000),
                    )

                if plan_step.agent == "coder" and plan_step.tool != (
                    "filesystem.write"
                ):
                    # O planner só grava propostas em steps com
                    # filesystem.write; sem o aviso, o coder alega ter
                    # criado arquivos que nunca são gravados.
                    extra_context += (
                        "\n<persistence>\n"
                        "Este step NÃO inclui filesystem.write: arquivos da "
                        "sua proposta NÃO serão gravados. Não afirme ter "
                        "criado arquivos. Coloque o resultado no campo "
                        "summary; use files somente se o plano tiver um "
                        "step filesystem.write.\n"
                        "</persistence>\n"
                    )

                step_started = time.monotonic()
                try:
                    if plan_step.agent == "researcher":
                        output_text = self.researcher.run(
                            goal=goal,
                            objective=plan_step.objective,
                            context=self.context() + extra_context,
                        )
                        result_text = output_text
                        last_answer = output_text
                    elif plan_step.agent == "coder":
                        proposal = self.coder.run(
                            goal=goal,
                            objective=plan_step.objective,
                            context=self.context() + extra_context,
                        )
                        result_text = json.dumps(
                            proposal.model_dump(), ensure_ascii=False
                        )
                        last_answer = proposal.summary
                    else:
                        raise ValueError(f"Agente não permitido: {plan_step.agent}")

                except Exception as exc:  # noqa: BLE001
                    self._log("step_error", step=plan_step.step, error=str(exc))
                    failure_reason = str(exc)
                    feedback = (
                        f"Step {plan_step.step} raised an error: {failure_reason}"
                    )
                    results.append(
                        {
                            "step": plan_step.step,
                            "status": "ERROR",
                            "reason": failure_reason,
                        }
                    )
                    plan_failed = True
                    break

                self._log(
                    "step_executed",
                    step=plan_step.step,
                    agent=plan_step.agent,
                    elapsed_s=round(time.monotonic() - step_started, 2),
                )

                self.memory.add(
                    self.run_id,
                    f"step_{plan_step.step}_result",
                    truncate(result_text, 12000),
                )

                try:
                    critic = self.critic.run(
                        goal=goal,
                        objective=plan_step.objective,
                        result=truncate(result_text, 12000),
                        extra_context=truncate(extra_context, 4000),
                    )
                except Exception as exc:  # noqa: BLE001
                    self._log("critic_error", step=plan_step.step, error=str(exc))
                    failure_reason = f"critic failed: {exc}"
                    feedback = f"Step {plan_step.step} critic crashed: {exc}"
                    results.append(
                        {
                            "step": plan_step.step,
                            "status": "ERROR",
                            "reason": failure_reason,
                        }
                    )
                    plan_failed = True
                    break

                self.memory.add(
                    self.run_id,
                    f"step_{plan_step.step}_critic",
                    json.dumps(critic.model_dump(), ensure_ascii=False),
                )

                if (
                    critic.confidence is not None
                    and critic.decision == "APPROVE"
                    and critic.confidence < self.min_confidence
                ):
                    critic.decision = "ESCALATE"
                    critic.problems.append(
                        f"confidence {critic.confidence:.2f} < "
                        f"min {self.min_confidence:.2f} — revisão humana exigida"
                    )

                self._log(
                    "critic_done",
                    step=plan_step.step,
                    decision=critic.decision,
                    score=critic.score,
                    confidence=critic.confidence,
                    engine=self.critic.engine.name,
                )

                if critic.decision == "ESCALATE":
                    # Fail-closed: probabilidade nunca autoriza sozinha.
                    # Para o run e devolve o estado para revisão humana.
                    results.append(
                        {
                            "step": plan_step.step,
                            "status": "ESCALATED",
                            "critic": critic.model_dump(),
                        }
                    )
                    self.memory.add(
                        self.run_id,
                        "escalation",
                        f"step {plan_step.step}: {critic.problems}",
                    )
                    return {
                        "run_id": self.run_id,
                        "status": "ESCALATED",
                        "results": results,
                        "answer": last_answer,
                        "reason": "Decisão com confiança insuficiente — revisão humana.",
                        "steps_used": self.supervisor.steps,
                        "replans": self.supervisor.replans,
                        "elapsed_seconds": round(self.supervisor.elapsed_seconds, 2),
                    }

                if critic.decision == "REJECT":
                    feedback = (
                        f"Step {plan_step.step} rejected.\n"
                        f"Problems: {critic.problems}\n"
                        f"Next action: {critic.next_action}"
                    )
                    results.append(
                        {
                            "step": plan_step.step,
                            "status": "REJECTED",
                            "critic": critic.model_dump(),
                        }
                    )
                    plan_failed = True
                    failure_reason = f"critic rejected step {plan_step.step}"
                    break

                result_entry = {
                    "step": plan_step.step,
                    "agent": plan_step.agent,
                    "status": "APPROVED",
                    "critic": critic.model_dump(),
                }

                if (
                    plan_step.agent == "coder"
                    and plan_step.tool == "filesystem.write"
                ):
                    try:
                        proposal_data = json.loads(result_text)
                    except json.JSONDecodeError as exc:
                        failure_reason = f"invalid proposal JSON: {exc}"
                        feedback = f"Step {plan_step.step}: {failure_reason}"
                        results.append(
                            {
                                "step": plan_step.step,
                                "status": "ERROR",
                                "reason": failure_reason,
                            }
                        )
                        plan_failed = True
                        break

                    files = proposal_data.get("files", []) or []
                    invalid = None
                    if not isinstance(files, list) or len(files) > 100:
                        invalid = "lista de arquivos inválida ou excede o limite de 100 arquivos"
                        files = []
                    pairs: list[tuple[str, str]] = []

                    for entry in files:
                        if not isinstance(entry, dict):
                            invalid = "entrada de arquivo inválida"
                            break
                        path = entry.get("path")
                        content = entry.get("content")
                        if not isinstance(path, str):
                            invalid = "path de arquivo inválido"
                            break
                        if not isinstance(content, str):
                            invalid = "conteúdo de arquivo inválido"
                            break
                        pairs.append((path, content))

                    if invalid:
                        feedback = f"Step {plan_step.step}: {invalid}"
                        results.append(
                            {
                                "step": plan_step.step,
                                "status": "ERROR",
                                "reason": invalid,
                            }
                        )
                        plan_failed = True
                        failure_reason = invalid
                        break

                    try:
                        written = self.execute_tool(
                            "filesystem.write", {"files": pairs}
                        )
                        result_entry["written_files"] = written
                        self.memory.add(
                            self.run_id,
                            "filesystem_write",
                            json.dumps(written, ensure_ascii=False),
                        )
                    except Exception as exc:  # noqa: BLE001
                        self._log("write_error", step=plan_step.step, error=str(exc))
                        failure_reason = str(exc)
                        feedback = (
                            f"Step {plan_step.step} failed to write: {failure_reason}"
                        )
                        results.append(
                            {
                                "step": plan_step.step,
                                "status": "ERROR",
                                "reason": failure_reason,
                            }
                        )
                        plan_failed = True
                        break

                elif plan_step.agent == "coder":
                    # Proposta aprovada mas o step não tem
                    # filesystem.write: nada é gravado. Deixa isso
                    # explícito no log em vez de silencioso.
                    try:
                        pending = json.loads(result_text).get("files") or []
                    except json.JSONDecodeError:
                        pending = []
                    if pending:
                        self._log(
                            "proposal_not_written",
                            step=plan_step.step,
                            files=len(pending),
                            reason="step sem filesystem.write",
                        )

                results.append(result_entry)
                feedback = ""

            if not plan_failed:
                self.memory.add(
                    self.run_id, "completion", "Run completed successfully."
                )
                return {
                    "run_id": self.run_id,
                    "status": "COMPLETED",
                    "results": results,
                    "answer": last_answer,
                    "steps_used": self.supervisor.steps,
                    "replans": self.supervisor.replans,
                    "elapsed_seconds": round(self.supervisor.elapsed_seconds, 2),
                }

            ok, reason = self.supervisor.authorize_replan()
            if not ok:
                return {
                    "run_id": self.run_id,
                    "status": "REPLAN_LIMIT",
                    "results": results,
                    "answer": last_answer,
                    "reason": reason,
                    "last_failure": failure_reason,
                    "steps_used": self.supervisor.steps,
                    "replans": self.supervisor.replans,
                }
