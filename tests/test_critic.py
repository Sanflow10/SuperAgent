import json

from agents.critic import Critic


class FakeRouter:
    def __init__(self, response):
        self.response = response

    def ask(self, role, system, prompt):
        return self.response


def test_critic_reject():
    payload = {"decision": "REJECT", "score": 0.2,
               "problems": ["e"], "next_action": "fix"}
    router = FakeRouter(f"```json\n{json.dumps(payload)}\n```")
    r = Critic(router, None, None).run("g", "o", "r")
    assert r.decision == "REJECT"


def test_critic_coerces_invalid():
    payload = {"decision": "MAYBE", "score": 0.5,
               "problems": [], "next_action": ""}
    router = FakeRouter(json.dumps(payload))
    r = Critic(router, None, None).run("g", "o", "r")
    assert r.decision == "REJECT"
