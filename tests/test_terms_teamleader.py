"""用语（扩到全系统）：对人、对 agent 都叫「首领」「打工猫」。
TeamLeader / Team Member / 打工仔 只留在兼容旧输入的角色别名（http.ROLE_ALIASES）里。"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
PKG = ROOT / "boxbox"


def test_no_old_terms_in_ui():
    s = (ROOT / "office/office.html").read_text(encoding="utf-8")
    assert 'label:lead?TR("d.leader"):id' in s
    assert 'label:lead?"TeamLeader"' not in s
    # 旧称呼只能留在兼容旧数据的判断里，不能当给人看的字
    assert ':"TeamLeader"' not in s
    assert ':"Team Member' not in s
    for page in ("stations.html", "index.html", "home.html", "settings.html", "doctor.html", "onboard.html") + tuple(
            sorted(p.name for p in (PKG / "static").glob("onboard-*.js"))):
        t = (PKG / "static" / page).read_text(encoding="utf-8")
        assert '"Team Member"' not in t, page
        assert "TeamLeader" not in t, page
        assert "打工仔" not in t, page


def test_templates_and_tool_descriptions_use_new_terms():
    """上岗模板、MCP 工具说明、自检、事件文字：给 agent 和给人看的都统一"""
    for p in list((PKG / "templates").glob("*.md")):
        t = p.read_text(encoding="utf-8")
        assert "TeamLeader" not in t and "Team Member" not in t, p.name
    for rel in ("facades/mcp_stdio.py", "facades/http.py", "dispatcher.py", "doctor.py"):
        for i, line in enumerate((PKG / rel).read_text(encoding="utf-8").splitlines(), 1):
            if "ROLE_ALIASES" in line or "normalize_role" in line or "TeamLeader / 首领 → leader" in line \
                    or "照着页面抄" in line:
                continue
            for m in re.finditer(r'"[^"\n]*"', line):                     # 只看字符串字面量
                assert "TeamLeader" not in m.group(0) and "Team Member" not in m.group(0), "%s:%d %s" % (rel, i, m.group(0))


if __name__ == "__main__":
    test_no_old_terms_in_ui()
    test_templates_and_tool_descriptions_use_new_terms()
    print("ok")
