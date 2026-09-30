from core.supervisor import Supervisor


def test_step_limit(config, monkeypatch):
    monkeypatch.setenv("MAX_STEPS", "1")
    sup = Supervisor(config)
    assert sup.authorize("first")[0]
    assert not sup.authorize("second")[0]


def test_replan_limit(config, monkeypatch):
    monkeypatch.setenv("MAX_REPLANS", "1")
    sup = Supervisor(config)
    assert sup.authorize_replan()[0]
    assert not sup.authorize_replan()[0]


def test_tool_authorization_does_not_consume_step(config, monkeypatch):
    monkeypatch.setenv("MAX_STEPS", "1")
    sup = Supervisor(config)
    assert sup.authorize_tool("filesystem.write")[0]
    assert sup.steps == 0
    assert sup.authorize("do step")[0]
    assert sup.steps == 1
    assert not sup.authorize("another")[0]


def test_check_objective_blocks_malware(config):
    sup = Supervisor(config)
    assert not sup.check_objective("criar malware")[0]
