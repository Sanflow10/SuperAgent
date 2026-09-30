import shutil

import pytest

from core.config import Config
from tools.filesystem import FilesystemTool
from tools.registry import ToolRegistry
from tools.sandbox import SandboxTool


def _tool(tmp_path, monkeypatch, **env):
    monkeypatch.setenv("ALLOW_SANDBOX", "true")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    config = Config()
    fs = FilesystemTool(config, workspace_dir=tmp_path)
    return SandboxTool(config, filesystem=fs)


def test_deny_by_default(config, tmp_path):
    """Sem ALLOW_SANDBOX=true a execução é recusada mesmo com script válido."""
    fs = FilesystemTool(config, workspace_dir=tmp_path)
    tool = SandboxTool(config, filesystem=fs)
    fs.write_many([("x.py", "print(1)")])
    with pytest.raises(PermissionError, match="ALLOW_SANDBOX"):
        tool.execute("x.py")


def test_registry_gate(config, tmp_path):
    registry = ToolRegistry(config, workspace=tmp_path)
    assert not registry.available("sandbox.execute")
    with pytest.raises(PermissionError):
        registry.execute("sandbox.execute", {"path": "x.py"})


def test_traversal_blocked(tmp_path, monkeypatch):
    tool = _tool(tmp_path, monkeypatch)
    with pytest.raises(PermissionError):
        tool.execute("../evil.py")


def test_absolute_blocked(tmp_path, monkeypatch):
    tool = _tool(tmp_path, monkeypatch)
    with pytest.raises(PermissionError):
        tool.execute("/etc/passwd")


def test_missing_script(tmp_path, monkeypatch):
    tool = _tool(tmp_path, monkeypatch)
    with pytest.raises(FileNotFoundError):
        tool.execute("nope.py")


def test_executes_and_captures(tmp_path, monkeypatch):
    tool = _tool(tmp_path, monkeypatch)
    tool.fs.write_many([("hello.py", "print('SANDBOX_OK')")])
    output = tool.execute("hello.py")
    assert "SANDBOX_OK" in output
    assert "exit_code" not in output
    assert "TIMEOUT" not in output


def test_exit_code_reported(tmp_path, monkeypatch):
    tool = _tool(tmp_path, monkeypatch)
    tool.fs.write_many([("bad.py", "import sys; print('x'); sys.exit(3)")])
    output = tool.execute("bad.py")
    assert "exit_code=3" in output
    assert "x" in output


def test_timeout_kills_runaway(tmp_path, monkeypatch):
    tool = _tool(tmp_path, monkeypatch, SANDBOX_TIMEOUT="2")
    tool.fs.write_many([("sleep.py", "import time\ntime.sleep(120)\n")])
    output = tool.execute("sleep.py")
    assert "TIMEOUT" in output


def test_network_denied_in_bwrap(tmp_path, monkeypatch):
    """SA-110: dentro do bwrap não há rota de rede (unshare-net)."""
    if shutil.which("bwrap") is None:
        pytest.skip("bwrap indisponível")

    tool = _tool(tmp_path, monkeypatch, SANDBOX_BACKEND="bwrap")
    if not tool._bwrap_usable():
        pytest.skip("bwrap não funcional neste host (user namespaces?)")

    tool.fs.write_many([(
        "net.py",
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 80), 2)\n"
        "    print('NET_OK')\n"
        "except Exception as exc:\n"
        "    print('NET_DENIED', type(exc).__name__)\n",
    )])
    output = tool.execute("net.py")
    assert "NET_DENIED" in output
    assert "NET_OK" not in output


def test_plain_backend_does_not_inherit_parent_env(tmp_path, monkeypatch):
    """Regressão de segurança: o backend plain herdava o ambiente do pai —
    o código gerado pelo LLM lia chaves (NVIDIA_*, DECISION_API_KEY) do
    host, e plain não nega rede. Agora o env é mínimo (PATH/HOME/LANG)."""
    monkeypatch.setenv("VAZAO_TEST_SECRET", "banana-123")
    tool = _tool(tmp_path, monkeypatch, SANDBOX_BACKEND="plain")
    tool.fs.write_many([(
        "env.py",
        "import os\n"
        "print('LEAK=', os.environ.get('VAZAO_TEST_SECRET'))\n"
        "print('KEYS=', [k for k in os.environ if 'KEY' in k or 'TOKEN' in k])\n",
    )])
    output = tool.execute("env.py")
    assert "banana-123" not in output
    assert "LEAK= None" in output
