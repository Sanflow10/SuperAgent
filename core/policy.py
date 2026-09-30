import re
from typing import ClassVar


class Policy:
    """
    Defense-in-depth taint-check + tool allowlist.
    Não substitui sandbox, SO ou isolamento Docker.
    """

    FORBIDDEN_PATTERNS: ClassVar[tuple[str, ...]] = (
        r"\bransomware\b",
        r"\bmalware\b",
        r"\bkeylogger\b",
        r"\bphishing\b",
        r"\bcredential\s+steal",
        r"\bcredential\s+harvest",
        r"\bcredential\s+dump",
        r"\bpassword\s+dump",
        r"\btoken\s+steal",
        r"\bsteal\s+password",
        r"\broubar\s+senha",
        r"\broubar\s+credencial",
        r"\bcredenciais\b.*\broubar",
        r"\bexfiltrat",
        r"\bexfiltra",
        r"\brm\s+-rf\s+/",
        r"\bchmod\s+777\b",
        r"\bdisable\s+security",
        r"\bdesativar\s+seguran",
        r"\bbackdoor\b",
    )

    ALLOWED_TOOLS: ClassVar[frozenset[str | None]] = frozenset({
        None,
        "filesystem.read",
        "filesystem.write",
        "sandbox.execute",
    })

    def __init__(self):
        self.patterns = [re.compile(p, re.IGNORECASE) for p in self.FORBIDDEN_PATTERNS]

    def check_goal(self, text: str):
        if not text or not text.strip():
            return False, "Objetivo vazio."

        for pattern in self.patterns:
            if pattern.search(text):
                return False, f"Bloqueado pela política: {pattern.pattern}"

        return True, "OK"

    def check_tool(self, tool: str | None):
        if tool not in self.ALLOWED_TOOLS:
            return False, f"Tool não permitida: {tool}"
        return True, "OK"
