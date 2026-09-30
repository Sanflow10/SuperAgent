from pathlib import Path

from core.config import Config
from core.paths import WORKSPACE


class FilesystemTool:

    name = "filesystem"

    def __init__(self, config: Config, workspace_dir: Path | None = None):
        self.config = config
        self.workspace_dir = (workspace_dir or WORKSPACE).resolve()

        self.allow_read = config.env_bool(
            "ALLOW_FILE_READ", "policy", "allow_file_read", default=True
        )
        self.allow_write = config.env_bool(
            "ALLOW_FILE_WRITE", "policy", "allow_file_write", default=True
        )

    def safe_target(self, name: str) -> Path:
        if not name or not name.strip():
            raise PermissionError("Nome de arquivo vazio.")

        if "\x00" in name:
            raise PermissionError("Nome de arquivo inválido.")

        raw_target = self.workspace_dir / name
        if any(part.is_symlink() for part in (self.workspace_dir, *raw_target.parents)):
            raise PermissionError("Symlink em caminho do workspace bloqueado.")
        target = raw_target.resolve()
        if target.is_symlink():
            raise PermissionError("Destino symlink bloqueado.")

        try:
            target.relative_to(self.workspace_dir)
        except ValueError as exc:
            raise PermissionError(
                f"Caminho fora do workspace bloqueado: {target}"
            ) from exc

        return target

    def read(self, name: str) -> str:
        if not self.allow_read:
            raise PermissionError("Leitura de arquivos desativada.")

        target = self.safe_target(name)

        if not target.exists():
            raise FileNotFoundError(target)

        if not target.is_file():
            raise IsADirectoryError(target)

        return target.read_text(encoding="utf-8")

    def write_many(self, files: list[tuple[str, str]]) -> list[str]:
        """Transactional multi-file write with rollback on failure."""

        if not self.allow_write:
            raise PermissionError("Escrita de arquivos desativada.")

        if not files:
            return []

        prepared: list[tuple[Path, str]] = []
        for name, content in files:
            if not isinstance(name, str) or not isinstance(content, str):
                raise TypeError("Nome e conteúdo devem ser str.")
            prepared.append((self.safe_target(name), content))

        written: list[tuple[Path, bool, str | None]] = []

        try:
            for target, content in prepared:
                existed = target.exists() and target.is_file()
                old = target.read_text(encoding="utf-8") if existed else None

                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")

                written.append((target, existed, old))

        except Exception:
            for target, existed, old in reversed(written):
                try:
                    if existed and old is not None:
                        target.write_text(old, encoding="utf-8")
                    else:
                        target.unlink(missing_ok=True)
                except OSError:
                    pass
            raise

        return [str(t) for t, _, _ in written]
