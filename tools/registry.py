from pathlib import Path

from core.config import Config
from tools.filesystem import FilesystemTool
from tools.sandbox import SandboxTool


class ToolRegistry:

    def __init__(self, config: Config, workspace: Path | None = None):
        self.config = config
        self.filesystem = FilesystemTool(config, workspace_dir=workspace)
        self.sandbox = SandboxTool(config, filesystem=self.filesystem)

    def available(self, name: str | None) -> bool:
        if name is None:
            return True
        if name == "filesystem.read":
            return self.filesystem.allow_read
        if name == "filesystem.write":
            return self.filesystem.allow_write
        if name == "sandbox.execute":
            return self.sandbox.allow_execute
        return False

    def execute(self, name: str, arguments: dict):
        if not self.available(name):
            raise PermissionError(f"Tool desativada: {name}")

        if name == "filesystem.read":
            return self.filesystem.read(arguments["path"])

        if name == "filesystem.write":
            if "files" in arguments:
                return self.filesystem.write_many(arguments["files"])
            return self.filesystem.write_many(
                [(arguments["path"], arguments["content"])]
            )

        if name == "sandbox.execute":
            return self.sandbox.execute(arguments["path"])

        raise PermissionError(f"Tool desconhecida: {name}")
