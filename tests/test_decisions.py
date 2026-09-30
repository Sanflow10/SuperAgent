"""Testes da DecisionEngine (V0.6): llm, rules, typed e ESCALATE."""

import json

import pytest
from pydantic import ValidationError

from core.config import Config
from core.decisions import (
    CriticDecision,
    LLMDecisionEngine,
    RuleDecisionEngine,
    build_engine,
)


class FakeRouter:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def ask(self, role, system, prompt):
        self.calls += 1
        return self.response


# ---------------------------------------------------------------- factory


def test_build_engine_default_is_llm(monkeypatch):
    monkeypatch.delenv("DECISION_ENGINE", raising=False)
    engine = build_engine(Config(), FakeRouter("x"))
    assert isinstance(engine, LLMDecisionEngine)


def test_build_engine_rules(monkeypatch):
    monkeypatch.setenv("DECISION_ENGINE", "rules")
    engine = build_engine(Config(), FakeRouter("x"))
    assert isinstance(engine, RuleDecisionEngine)


def test_build_engine_unknown_raises(monkeypatch):
    monkeypatch.setenv("DECISION_ENGINE", "wat")
    with pytest.raises(ValueError, match="DECISION_ENGINE"):
        build_engine(Config(), FakeRouter("x"))


def test_build_engine_typed_requires_url_and_model(monkeypatch):
    monkeypatch.setenv("DECISION_ENGINE", "typed")
    monkeypatch.delenv("DECISION_URL", raising=False)
    monkeypatch.delenv("DECISION_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="DECISION_URL"):
        build_engine(Config(), FakeRouter("x"))


# ---------------------------------------------------------------- rules


def test_rules_rejects_empty_result():
    d = RuleDecisionEngine().decide("g", "o", "   ")
    assert d.decision == "REJECT"
    assert "resultado vazio" in d.problems


def test_rules_rejects_timeout_marker():
    d = RuleDecisionEngine().decide("g", "o", "ok", extra_context="[TIMEOUT após 30s]")
    assert d.decision == "REJECT"


def test_rules_rejects_nonzero_exit_code():
    d = RuleDecisionEngine().decide("g", "o", "[exit_code=1]\nerro fatal")
    assert d.decision == "REJECT"


def test_rules_rejects_traceback():
    d = RuleDecisionEngine().decide(
        "g", "o", "Traceback (most recent call last):\n  File ..."
    )
    assert d.decision == "REJECT"


def test_rules_approves_clean_result_without_confidence():
    """Rules é sanity gate: aprova sem confidence (não autoriza nada)."""
    d = RuleDecisionEngine().decide("g", "o", "resultado limpo e completo")
    assert d.decision == "APPROVE"
    assert d.confidence is None


# ---------------------------------------------------------------- llm engine


def test_llm_engine_parses_and_coerces_invalid():
    payload = {"decision": "MAYBE", "score": 0.5, "problems": [], "next_action": ""}
    engine = LLMDecisionEngine(FakeRouter(json.dumps(payload)))
    d = engine.decide("g", "o", "r")
    assert d.decision == "REJECT"  # fail-closed


def test_llm_engine_parses_confidence_when_present():
    payload = {
        "decision": "APPROVE",
        "score": 0.9,
        "problems": [],
        "next_action": "",
        "confidence": 0.42,
    }
    engine = LLMDecisionEngine(FakeRouter(json.dumps(payload)))
    d = engine.decide("g", "o", "r")
    assert d.decision == "APPROVE"
    assert d.confidence == pytest.approx(0.42)


# ---------------------------------------------------------------- critic decision


def test_critic_decision_confidence_out_of_range_fails():
    with pytest.raises(ValidationError):
        CriticDecision(decision="APPROVE", score=0.9, confidence=1.5)


def test_critic_decision_score_out_of_range_fails():
    with pytest.raises(ValidationError):
        CriticDecision(decision="APPROVE", score=2.0)
