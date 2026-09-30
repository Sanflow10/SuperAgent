import json

import pytest

from agents.planner import Planner


class FakeRouter:
    def __init__(self, response):
        self.response = response

    def ask(self, role, system, prompt):
        return self.response


def test_planner_with_fence():
    payload = {
        "steps": [
            {"step": 1, "agent": "researcher", "objective": "x",
             "tool": None, "path": None}
        ]
    }
    router = FakeRouter(f"```json\n{json.dumps(payload)}\n```")
    plan = Planner(router, None, None).run("goal")
    assert plan.steps[0].agent == "researcher"


def test_read_requires_path():
    payload = {
        "steps": [
            {"step": 1, "agent": "researcher", "objective": "x",
             "tool": "filesystem.read", "path": None}
        ]
    }
    with pytest.raises(ValueError, match="path"):
        Planner(FakeRouter(json.dumps(payload)), None, None).run("g")


def test_read_accepts_valid_path():
    payload = {
        "steps": [
            {"step": 1, "agent": "researcher", "objective": "x",
             "tool": "filesystem.read", "path": "config.yaml"}
        ]
    }
    plan = Planner(FakeRouter(json.dumps(payload)), None, None).run("g")
    assert plan.steps[0].path == "config.yaml"


def test_rejects_absolute_path():
    payload = {
        "steps": [
            {"step": 1, "agent": "researcher", "objective": "x",
             "tool": "filesystem.read", "path": "/etc/passwd"}
        ]
    }
    with pytest.raises(ValueError, match="absoluto"):
        Planner(FakeRouter(json.dumps(payload)), None, None).run("g")


def test_rejects_traversal():
    payload = {
        "steps": [
            {"step": 1, "agent": "researcher", "objective": "x",
             "tool": "filesystem.read", "path": "../secrets"}
        ]
    }
    with pytest.raises(ValueError, match="ravessia"):
        Planner(FakeRouter(json.dumps(payload)), None, None).run("g")


def test_write_requires_coder():
    payload = {
        "steps": [
            {"step": 1, "agent": "researcher", "objective": "x",
             "tool": "filesystem.write", "path": None}
        ]
    }
    with pytest.raises(ValueError, match="coder"):
        Planner(FakeRouter(json.dumps(payload)), None, None).run("g")


def test_path_only_with_read():
    payload = {
        "steps": [
            {"step": 1, "agent": "coder", "objective": "x",
             "tool": "filesystem.write", "path": "x.txt"}
        ]
    }
    with pytest.raises(ValueError, match=r"filesystem\.read"):
        Planner(FakeRouter(json.dumps(payload)), None, None).run("g")


def test_sandbox_execute_requires_path():
    payload = {
        "steps": [
            {"step": 1, "agent": "coder", "objective": "x",
             "tool": "sandbox.execute", "path": None}
        ]
    }
    with pytest.raises(ValueError, match="path"):
        Planner(FakeRouter(json.dumps(payload)), None, None).run("g")


def test_sandbox_execute_valid_path():
    payload = {
        "steps": [
            {"step": 1, "agent": "researcher", "objective": "x",
             "tool": "sandbox.execute", "path": "build.py"}
        ]
    }
    plan = Planner(FakeRouter(json.dumps(payload)), None, None).run("g")
    assert plan.steps[0].path == "build.py"
