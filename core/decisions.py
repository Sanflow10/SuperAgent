"""Camada de decisão — DecisionEngine (V0.6).

Separação de responsabilidades (padrão decision-layer):

- Código determinístico: regras, permissões, limites e efeitos colaterais
  vivem no Supervisor/Policy — nunca aqui.
- Motor de decisão: julgamento semântico ESTREITO, tipado, com confiança
  opcional. Emite sinais (APPROVE/REJECT/ESCALATE), nunca autorizações.
- LLM: linguagem — plano, redação, explicação.

Confidence não é autorização: quando `confidence < DECISION_MIN_CONFIDENCE`
o orquestrador converte APPROVE em ESCALATE e interrompe o run para revisão
humana (fail-closed). Nenhuma decisão probabilística vira efeito colateral.

Engines:

- llm    (default): o crítico clássico — LLM gera JSON estrito e validado.
- rules  : determinístico, offline, sem rede — sanity gate de falhas concretas.
- typed  : endpoint OpenAI-compatible de decisão tipada (Jev via gateway,
           Laya, classificador local) — JSON estrito, temperature 0.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod

import requests
from pydantic import BaseModel, Field, ValidationError

from core.config import Config
from core.util import parse_json_llm


decision_logger = logging.getLogger("superagent.decisions")

VALID_DECISIONS = {"APPROVE", "REJECT", "ESCALATE"}


class CriticDecision(BaseModel):
    decision: str
    score: float = Field(ge=0.0, le=1.0)
    problems: list[str] = Field(default_factory=list)
    next_action: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    def fail_closed(self) -> CriticDecision:
        """Normaliza para um conjunto fechado; desconhecido vira REJECT."""
        if self.decision not in VALID_DECISIONS:
            decision_logger.warning(
                "invalid_critic_decision",
                extra={
                    "event": "invalid_critic_decision",
                    "raw_decision": self.decision,
                },
            )
            self.decision = "REJECT"
        return self


class DecisionEngine(ABC):
    """Emite sinais tipados; nunca autoriza efeitos colaterais."""

    name = "engine"

    @abstractmethod
    def decide(
        self,
        goal: str,
        objective: str,
        result: str,
        extra_context: str = "",
    ) -> CriticDecision:
        raise NotImplementedError


class LLMDecisionEngine(DecisionEngine):
    """Crítico via LLM (comportamento clássico da V0.5/V0.6)."""

    name = "llm"

    def __init__(self, router):
        self.router = router

    def decide(
        self,
        goal: str,
        objective: str,
        result: str,
        extra_context: str = "",
    ) -> CriticDecision:
        system = """
Você é o CRITIC.

Avalie o resultado produzido por outro agente.

Procure: erro factual, objetivo não cumprido, informação inventada,
código inseguro, caminho de arquivo inseguro, tentativa de contornar
política, resultado incompleto.

Responda SOMENTE JSON:

{
  "decision": "APPROVE",
  "score": 0.95,
  "problems": [],
  "next_action": ""
}

decision deve ser APPROVE ou REJECT.
"""

        prompt = f"""
<goal>
{goal}
</goal>

<objective>
{objective}
</objective>

<provided_context>
{extra_context}
</provided_context>

<result>
{result}
</result>

Faça uma avaliação rigorosa.
"""

        raw = self.router.ask("critic", system, prompt)
        try:
            data = parse_json_llm(raw)
            return CriticDecision.model_validate(data).fail_closed()
        except (ValueError, ValidationError) as exc:
            # Deixa a resposta crua diagnosticável no log (sem ela, uma
            # falha intermitente do backend é invisível).
            decision_logger.warning(
                "critic_unparseable",
                extra={
                    "event": "critic_unparseable",
                    "error": str(exc)[:300],
                    "raw_snippet": raw[:400],
                },
            )
            raise


class RuleDecisionEngine(DecisionEngine):
    """Sanity gate determinístico — offline, sem LLM, sem rede.

    Não julga qualidade semântica; detecta falhas concretas e objetivas
    (resultado vazio, timeout, exit code != 0, traceback). Qualquer marcador
    de falha => REJECT. Sem marcador => APPROVE com score moderado, porque
    ausência de erro não é prova de qualidade.
    """

    name = "rules"

    FAILURE_MARKERS = (
        "[TIMEOUT",
        "[exit_code=",
        "Traceback (most recent call last)",
    )

    def decide(
        self,
        goal: str,
        objective: str,
        result: str,
        extra_context: str = "",
    ) -> CriticDecision:
        combined = f"{result}\n{extra_context}"

        if not result.strip():
            return CriticDecision(
                decision="REJECT",
                score=0.0,
                problems=["resultado vazio"],
                next_action="Produza um resultado não vazio.",
            )

        hits = [marker for marker in self.FAILURE_MARKERS if marker in combined]
        if hits:
            problems = [f"marcador de falha presente: {marker}" for marker in hits]
            return CriticDecision(
                decision="REJECT",
                score=0.1,
                problems=problems,
                next_action="Elimine a falha antes de prosseguir.",
            )

        return CriticDecision(
            decision="APPROVE",
            score=0.7,
            problems=[],
            next_action="",
        )


class TypedDecisionEngine(DecisionEngine):
    """Endpoint OpenAI-compatible de decisão tipada.

    Fala com Jev (via gateway), Laya, ou qualquer classificador local que
    exponha /chat/completions. Exige DECISION_URL e DECISION_MODEL.
    temperature fixa em 0; saída validada fail-closed.
    """

    name = "typed"

    def __init__(self, config: Config):
        self.url = config.env_str(
            "DECISION_URL", "decision", "url", default=""
        ).rstrip("/")
        self.model = config.env_str(
            "DECISION_MODEL", "decision", "model", default=""
        )
        self.api_key = os.getenv("DECISION_API_KEY", "")
        self.timeout = config.env_int(
            "DECISION_TIMEOUT", "decision", "timeout", default=60
        )

        if not self.url or not self.model:
            raise RuntimeError(
                "DECISION_ENGINE=typed exige DECISION_URL e DECISION_MODEL."
            )

    def decide(
        self,
        goal: str,
        objective: str,
        result: str,
        extra_context: str = "",
    ) -> CriticDecision:
        system = (
            "Você é um motor de decisão tipada. Responda SOMENTE JSON, sem prosa: "
            '{"decision": "APPROVE" | "REJECT" | "ESCALATE", '
            '"score": 0.0-1.0, "confidence": 0.0-1.0, '
            '"problems": ["..."], "next_action": "..."}'
        )
        prompt = (
            f"<goal>\n{goal}\n</goal>\n\n"
            f"<objective>\n{objective}\n</objective>\n\n"
            f"<provided_context>\n{extra_context}\n</provided_context>\n\n"
            f"<result>\n{result}\n</result>"
        )

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = requests.post(
            f"{self.url}/chat/completions",
            json={
                "model": self.model,
                "temperature": 0.0,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        if not content:
            raise RuntimeError("Motor de decisão tipada retornou conteúdo vazio.")

        parsed = parse_json_llm(content)
        return CriticDecision.model_validate(parsed).fail_closed()


def build_engine(config: Config, router) -> DecisionEngine:
    """Factory: DECISION_ENGINE=llm|rules|typed (default llm)."""
    kind = config.env_str(
        "DECISION_ENGINE", "decision", "engine", default="llm"
    ).strip().lower()

    if kind == "llm":
        return LLMDecisionEngine(router)
    if kind == "rules":
        return RuleDecisionEngine()
    if kind == "typed":
        return TypedDecisionEngine(config)

    raise ValueError(
        f"DECISION_ENGINE desconhecido: {kind!r} (esperado: llm, rules ou typed)"
    )
