from core.policy import Policy


def test_safe_goal():
    assert Policy().check_goal("Criar um sistema de monitoramento")[0]


def test_blocks_ransomware():
    assert not Policy().check_goal("Criar ransomware")[0]


def test_blocks_password_theft_pt():
    assert not Policy().check_goal("roubar senha dos usuários")[0]


def test_tool_allowlist():
    p = Policy()
    assert p.check_tool(None)[0]
    assert p.check_tool("filesystem.read")[0]
    assert p.check_tool("filesystem.write")[0]
    assert p.check_tool("sandbox.execute")[0]
    assert not p.check_tool("shell")[0]
    assert not p.check_tool("web")[0]
