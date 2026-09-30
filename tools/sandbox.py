import os
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from core.config import Config


class SandboxTool:
    """
    Execução isolada de scripts Python gerados pelo coder.

    Backends:
      - bwrap: namespaces (user/pid/net/ipc/uts), root read-only,
        somente script + venv visíveis, tmpfs em /tmp, SEM rede.
        Isolamento forte.
      - plain: subprocess + RLIMIT_CPU/AS/FSIZE/NOFILE + timeout com
        killpg. Isolamento REDUZIDO — não nega rede; usado apenas
        quando o bwrap está indisponível.

    Deny by default: exige ALLOW_SANDBOX=true.
    """

    name = "sandbox"

    def __init__(self, config: Config, filesystem=None):
        self.config = config
        self.fs = filesystem

        self.allow_execute = config.env_bool(
            "ALLOW_SANDBOX", "policy", "allow_sandbox", default=False
        )
        self.backend = config.env_str(
            "SANDBOX_BACKEND", "sandbox", "backend", default="auto"
        ).lower()
        self.timeout = config.env_int(
            "SANDBOX_TIMEOUT", "sandbox", "timeout", default=30
        )
        self.memory_mb = config.env_int(
            "SANDBOX_MEMORY_MB", "sandbox", "memory_mb", default=256
        )
        self.max_output = config.env_int(
            "SANDBOX_MAX_OUTPUT", "sandbox", "max_output", default=8000
        )

        self._probe: bool | None = None

    # ------------------------------------------------------------------ gates

    def safe_script(self, name: str) -> Path:
        if self.fs is None:
            raise PermissionError("Sandbox sem FilesystemTool associado.")
        target = self.fs.safe_target(name)
        if not target.exists():
            raise FileNotFoundError(f"Script não encontrado: {name}")
        if not target.is_file():
            raise IsADirectoryError(target)
        return target

    # --------------------------------------------------------------- execução

    def execute(self, path: str) -> str:
        if not self.allow_execute:
            raise PermissionError("Sandbox desativada (ALLOW_SANDBOX=false).")

        script = self.safe_script(path)
        backend = self._pick_backend()

        if backend == "bwrap":
            output, code = self._run_bwrap(script)
            if self.backend == "auto" and (output or "").lstrip().startswith("bwrap:"):
                output, code = self._run_plain(script)
        else:
            output, code = self._run_plain(script)

        header = ""
        if code is None:
            header = f"[TIMEOUT após {self.timeout}s]\n"
        elif code != 0:
            header = f"[exit_code={code}]\n"

        text = header + (output or "")
        text = text.replace("</sandbox_output>", "<\\/sandbox_output>")

        if len(text) > self.max_output:
            text = text[: self.max_output] + "\n[TRUNCATED]"
        return text

    def _pick_backend(self) -> str:
        if self.backend == "plain":
            return "plain"
        if self.backend == "bwrap":
            if shutil.which("bwrap") is None or not self._bwrap_usable():
                raise PermissionError(
                    "SANDBOX_BACKEND=bwrap indisponível neste host."
                )
            return "bwrap"
        if shutil.which("bwrap") and self._bwrap_usable():
            return "bwrap"
        return "plain"

    def _bwrap_usable(self) -> bool:
        if self._probe is None:
            try:
                proc = subprocess.run(
                    self._bwrap_command(["/bin/true"], []),
                    capture_output=True,
                    timeout=15,
                )
                self._probe = proc.returncode == 0
            except (OSError, subprocess.SubprocessError):
                self._probe = False
        return bool(self._probe)

    # --------------------------------------------------------------- limites

    def _limits(self):
        def apply() -> None:
            cpu = max(1, self.timeout)
            memory = self.memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
            resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
            resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
            resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024,) * 2)

        return apply

    def _spawn(
        self,
        command: list[str],
        cwd: Path,
        *,
        inherit_env: bool = True,
    ) -> tuple[str, int | None]:
        # Backend plain: NÃO herda o ambiente do processo pai — o código
        # gerado pelo LLM não pode ler chaves (NVIDIA_*, DECISION_API_KEY)
        # do host. bwrap herda aqui porque limpa o env dentro (--clearenv).
        env = None
        if not inherit_env:
            env = {
                "PATH": "/usr/bin:/bin",
                "HOME": str(cwd),
                "LANG": "C.UTF-8",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            start_new_session=True,
            preexec_fn=self._limits(),
            env=env,
        )
        try:
            out, _ = process.communicate(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                process.kill()
            out, _ = process.communicate()
            return out or "", None
        return out or "", process.returncode

    # -------------------------------------------------------------- backends

    def _bwrap_command(self, argv: list[str], binds: list[str]) -> list[str]:
        command = [
            "bwrap",
            "--die-with-parent",
            "--unshare-user",
            "--unshare-pid",
            "--unshare-net",
            "--unshare-ipc",
            "--unshare-uts",
            "--ro-bind", "/usr", "/usr",
            "--ro-bind", "/bin", "/bin",
            "--ro-bind", "/sbin", "/sbin",
            "--ro-bind", "/lib", "/lib",
            "--ro-bind", "/lib64", "/lib64",
            "--ro-bind", "/etc", "/etc",
            "--proc", "/proc",
            "--dev", "/dev",
            "--tmpfs", "/tmp",
        ]

        venv = Path(sys.prefix).resolve()
        if not str(venv).startswith(("/usr", "/lib", "/bin", "/sbin")):
            command += ["--ro-bind", str(venv), str(venv)]

        for source in binds:
            command += ["--ro-bind", source, source]

        command += [
            "--chdir", "/tmp",
            "--clearenv",
            "--setenv", "HOME", "/tmp",
            "--setenv", "PATH", "/usr/bin:/bin",
            "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
        ]
        return command + argv

    def _run_plain(self, script: Path) -> tuple[str, int | None]:
        cwd = Path(tempfile.mkdtemp(prefix="sa_sandbox_"))
        try:
            return self._spawn(
                [sys.executable, "-I", str(script)],
                cwd,
                inherit_env=False,
            )
        finally:
            shutil.rmtree(cwd, ignore_errors=True)

    def _run_bwrap(self, script: Path) -> tuple[str, int | None]:
        command = self._bwrap_command(
            [sys.executable, "-I", str(script)], [str(script)]
        )
        return self._spawn(command, Path("/"))
