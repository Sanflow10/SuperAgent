import time

from core.config import Config
from core.policy import Policy


class Supervisor:
    def __init__(self, config: Config):
        self.config = config
        self.policy = Policy()

        self.max_steps = config.env_int("MAX_STEPS", "limits", "max_steps", default=20)
        self.max_replans = config.env_int("MAX_REPLANS", "limits", "max_replans", default=3)
        self.max_depth = config.env_int("MAX_AGENT_DEPTH", "limits", "max_depth", default=3)
        self.max_minutes = config.env_int(
            "MAX_RUNTIME_MINUTES", "limits", "max_runtime_minutes", default=30
        )

        self.steps = 0
        self.replans = 0
        self.started = time.monotonic()

    def check_goal(self, text: str):
        return self.policy.check_goal(text)

    def check_objective(self, text: str):
        return self.policy.check_goal(text)

    def authorize(self, action: str, *, depth: int = 0, tool: str | None = None):
        if time.monotonic() - self.started >= self.max_minutes * 60:
            return False, "Limite de tempo excedido."

        if self.steps >= self.max_steps:
            return False, "Limite de etapas excedido."

        if depth > self.max_depth:
            return False, "Profundidade máxima excedida."

        if tool is not None:
            ok, reason = self.policy.check_tool(tool)
            if not ok:
                return False, reason

        if not action or not action.strip():
            return False, "Ação vazia."

        self.steps += 1
        return True, "OK"

    def authorize_tool(self, tool: str):
        """Does NOT consume a step — tool lives inside an authorized step."""
        return self.policy.check_tool(tool)

    def authorize_replan(self):
        if self.replans >= self.max_replans:
            return False, "Limite de replans excedido."
        self.replans += 1
        return True, "OK"

    @property
    def elapsed_seconds(self):
        return time.monotonic() - self.started
