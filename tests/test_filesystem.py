import pytest

from tools.filesystem import FilesystemTool


@pytest.fixture
def tool(config, tmp_path):
    return FilesystemTool(config, workspace_dir=tmp_path)


def test_safe_workspace_path(tool, tmp_path):
    assert str(tool.safe_target("hello.txt")).startswith(str(tmp_path.resolve()))


def test_parent_escape(tool):
    with pytest.raises(PermissionError):
        tool.safe_target("../../etc/passwd")


def test_absolute_path(tool):
    with pytest.raises(PermissionError):
        tool.safe_target("/etc/passwd")


def test_prefix_attack_blocked(tool, tmp_path):
    """Regression: 'workspace_evil' must not pass startswith checks."""
    sibling = tmp_path.parent / "workspace_evil"
    sibling.mkdir(exist_ok=True)
    (sibling / "pwn.txt").write_text("x", encoding="utf-8")

    with pytest.raises(PermissionError):
        tool.safe_target("../workspace_evil/pwn.txt")


def test_write_and_read(tool):
    tool.write_many([("sub/hello.txt", "hi")])
    assert tool.read("sub/hello.txt") == "hi"


def test_write_many_rollback_on_error(tool, tmp_path):
    with pytest.raises(PermissionError):
        tool.write_many([("ok.txt", "content"), ("../escape.txt", "bad")])
    assert not (tmp_path / "ok.txt").exists()
