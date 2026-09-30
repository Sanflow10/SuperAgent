from agents.base import Agent
from core.decisions import (
    CriticDecision,
    DecisionEngine,
    LLMDecisionEngine,
)


class Critic(Agent):
    """Fachada: avalia resultados através de um DecisionEngine pluggable.

    Engine padrão: LLMDecisionEngine (comportamento clássico).
    Seleção via DECISION_ENGINE=llm|rules|typed (ver core/decisions.py).
    """

    name = "critic"

    def __init__(self, router, memory, logger, engine: DecisionEngine | None = None):
        super().__init__(router, memory, logger)
        self.engine = engine if engine is not None else LLMDecisionEngine(router)

    def run(
        self,
        goal: str,
        objective: str,
        result: str,
        extra_context: str = "",
    ) -> CriticDecision:
        return self.engine.decide(goal, objective, result, extra_context)
