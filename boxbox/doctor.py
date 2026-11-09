"""自检（工作计划 4.4 后端）：看板 doctor 页和「复制诊断信息」的数据来源（§17.2 第 6、7 条）。

查这些：Python 版本（源码运行时才查，exe 里是打包进来的）、数据目录能不能写、工位里有没有首领、
核心在不在听、Pi 装没装（只有用 Pi 的工位才查）、各 AI 软件里有没有连上猫猫盒子、出厂模板齐不齐。
盒子自己拉起来的工位（Pi）不用连猫猫盒子，不查它。

诊断文本会被用户复制贴到 issue 里，所以：不打印任何环境变量的值（§12），路径里的用户名
换成 ~，看着像密钥的串换成 ***。本模块只读：只检测、只给「怎么办」，不替用户动手修
（不提供一键修复：exe 是打包好的，坏了的东西让用户照提示自己处理或重装）。
每项检查自己 try/except，坏了一项不能连累整页。仅标准库。
"""
from __future__ import annotations

import dataclasses
import json
import os
import platform
import re
import sys
import urllib.request
from pathlib import Path

from . import config, connectors, i18n, tasks

TEMPLATE_NAMES = ("leader.md", "leader.en.md", "member.md", "member.en.md",
                  "scheduled-file-member.md", "scheduled-file-member.en.md")
PI_NPM_PKG = "@earendil-works/pi-coding-agent"


@dataclasses.dataclass
class Check:
    """一项检查的结果。ok 为 None 表示跳过（这项不适用）；fix 是不过时给用户看的「怎么办」。"""

    id: str
    label: str
    ok: bool | None
    detail: str = ""
    fix: str = ""


def check_python(lang: str | None = None) -> Check:
    """本机 Python 要 3.11 以上（要 tomllib 读写 codex 的配置）。"""
    v = platform.python_version()
    label = i18n.t("doctor.label.python", lang)
    if sys.version_info >= (3, 11):
        return Check("python", label, True, v, "")
    return Check("python", label, False, v, i18n.t("doctor.python.fix", lang))


def check_data_dir(data_dir: Path | None = None, lang: str | None = None) -> Check:
    """数据目录在、是目录、并且能真的写一个临时文件再删掉。
    目录不在算不过；盒子启动时会自己建，所以「怎么办」是重开程序。"""
    p = Path(data_dir) if data_dir is not None else Path(config.DATA)
    label = i18n.t("doctor.label.data_dir", lang)
    if not p.exists():
        return Check("data_dir", label, False, i18n.t("doctor.data_dir.missing", lang, path=p),
                     i18n.t("doctor.data_dir.missing.fix", lang))
    if not p.is_dir():
        return Check("data_dir", label, False, i18n.t("doctor.data_dir.notdir", lang, path=p),
                     i18n.t("doctor.data_dir.notdir.fix", lang))
    try:
        probe = p / (".doctor-probe-%d.tmp" % os.getpid())
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as e:
        return Check("data_dir", label, False, i18n.t("doctor.data_dir.nowrite", lang, path=p, why=e),
                     i18n.t("doctor.data_dir.nowrite.fix", lang))
    return Check("data_dir", label, True, i18n.t("doctor.data_dir.ok", lang, path=p), "")


def check_leader(stations: list[dict] | None = None, lang: str | None = None) -> Check:
    """至少有一个启用的首领。多个首领各看自己派的卡，自检也算通过。"""
    sts = stations if stations is not None else config.stations()
    label = i18n.t("doctor.label.leader", lang)
    leaders = [str(s.get("id")) for s in sts
               if s.get("role") == "leader" and s.get("enabled", True)]
    if len(leaders) == 1:
        return Check("leader", label, True, i18n.t("doctor.leader.ok", lang, sid=leaders[0]), "")
    if not leaders:
        return Check("leader", label, False, i18n.t("doctor.leader.none", lang),
                     i18n.t("doctor.leader.none.fix", lang))
    names = i18n.t("list.sep", lang).join(leaders)
    return Check("leader", label, True, i18n.t("doctor.leader.many", lang, n=len(leaders), names=names), "")


def check_core(core_url: str | None, timeout_s: float = 2.0, lang: str | None = None) -> Check:
    """盒子在本机 HTTP 上；GET /api/meta 通了就是在听。"""
    label = i18n.t("doctor.label.core", lang)
    if not core_url:
        return Check("core", label, None, i18n.t("doctor.core.skip", lang), "")
    url = core_url.rstrip("/") + "/api/meta"
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as r:  # noqa: S310 - 本机 127.0.0.1
            doc = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # 连不上/超时/返回不是 JSON，都算「没在听」
        return Check("core", label, False, i18n.t("doctor.core.down", lang, url=core_url, why=_short(e)),
                     i18n.t("doctor.core.down.fix", lang))
    leader = doc.get("leader") or i18n.t("doctor.core.no_leader", lang)
    return Check("core", label, True, i18n.t("doctor.core.ok", lang, url=core_url, leader=leader), "")


def check_pi(stations: list[dict] | None = None, lang: str | None = None) -> Check:
    """Pi 能用：exe 自带的优先，没有再找系统里装的 npm 全局包。只有工位里用了 Pi 才需要查。"""
    from . import pi_config
    sts = stations if stations is not None else config.stations()
    label = i18n.t("doctor.label.pi", lang)
    if not any(s.get("client") == "pi" for s in sts):
        return Check("pi", label, None, i18n.t("doctor.pi.skip", lang), "")
    rt = pi_config.runtime()
    ver = ("Pi %s" % rt["pi_version"]) if rt.get("pi_version") else "Pi"
    if rt["source"] == "bundled":
        return Check("pi", label, True, i18n.t("doctor.pi.bundled", lang, ver=ver, node=rt.get("node_version") or "?"), "")
    if rt["source"] == "system":
        return Check("pi", label, True, i18n.t("doctor.pi.system", lang, ver=ver, cli=rt["cli"]), "")
    return Check("pi", label, False, i18n.t("doctor.pi.missing", lang),
                 i18n.t("doctor.pi.missing.fix", lang, pkg=PI_NPM_PKG))


def check_pi_key(station: dict, lang: str | None = None) -> Check:
    """一个 Pi 工位的 API key 到底有没有（只看 data/secrets.json 里存的那一份）。不显示值。"""
    from . import pi_config
    sid = str(station.get("id") or "")
    cid = "key:%s" % sid
    label = i18n.t("doctor.label.key", lang, sid=sid)
    if pi_config.key_available(station):
        return Check(cid, label, True, i18n.t("doctor.key.ok", lang, src="data/secrets.json"), "")
    return Check(cid, label, False, i18n.t("doctor.key.missing", lang),
                 i18n.t("doctor.key.missing.fix", lang))


def _template_ok(f: Path) -> bool:
    try:
        return f.is_file() and f.stat().st_size > 0
    except OSError:
        return False


def check_templates(pkg_dir: Path | None = None, lang: str | None = None) -> Check:
    """出厂模板都在、都非空；缺哪个写进 detail。
    用户自己那份在 data\\templates（改过就以它为准），包里那份在打包临时目录里——路径不给人看。"""
    label = i18n.t("doctor.label.templates", lang)
    if pkg_dir is not None:
        d = Path(pkg_dir)
        bad = [n for n in TEMPLATE_NAMES if not _template_ok(d / n)]
        if not bad:
            return Check("templates", label, True, i18n.t("doctor.templates.ok", lang), "")
        return Check("templates", label, False, i18n.t("doctor.templates.missing", lang, names=i18n.t("list.sep", lang).join(bad)),
                     i18n.t("doctor.templates.missing.fix", lang))
    user_dir = Path(config.DATA) / "templates"
    pkg_dir2 = Path(tasks.PKG_TEMPLATES)
    bad = []
    for name in TEMPLATE_NAMES:
        if _template_ok(user_dir / name) or _template_ok(pkg_dir2 / name):
            continue
        bad.append(name)
    if bad:
        return Check("templates", label, False, i18n.t("doctor.templates.missing", lang, names=i18n.t("list.sep", lang).join(bad)),
                     i18n.t("doctor.templates.missing.fix", lang))
    if all(_template_ok(user_dir / n) for n in TEMPLATE_NAMES):
        return Check("templates", label, True, i18n.t("doctor.templates.ok_path", lang, path=user_dir), "")
    return Check("templates", label, True, i18n.t("doctor.templates.ok", lang), "")


def is_box_run_station(station: dict) -> bool:
    """这个工位是不是盒子自己拉起来的（Pi）：这种工位不用在 AI 软件里连猫猫盒子。"""
    return str(station.get("client") or "") == "pi" or str(station.get("runner") or "") == "once"


def mcp_label(station: dict, lang: str | None = None) -> str:
    """连接那项的标题：首领的写「首领那个软件」，别的工位写「工位「X」的软件」。"""
    sid = str(station.get("id") or "")
    if station.get("role") == "leader":
        return i18n.t("doctor.label.leader_app", lang)
    return i18n.t("doctor.label.station_app", lang, sid=sid)


def check_mcp(station: dict, project_dir: str | None = None, home: str | None = None,
              lang: str | None = None) -> Check:
    """某个工位的连接在不在（在不在且指向这个工位）。"""
    sid = str(station.get("id") or "")
    client = str(station.get("client") or "")
    cid = "mcp:%s" % sid
    label = mcp_label(station, lang)
    try:
        known = connectors.load()
    except (OSError, ValueError) as e:
        return Check(cid, label, False, i18n.t("doctor.mcp.read_fail", lang, why=_short(e)),
                     i18n.t("doctor.mcp.read_fail.fix", lang))
    if client not in known:
        return Check(cid, label, None, i18n.t("doctor.mcp.skip_client", lang, client=client or i18n.t("doctor.empty", lang)), "")
    st = connectors.status(client, project_dir, home)
    if st.get("path") is None:
        return Check(cid, label, None, i18n.t("doctor.mcp.no_path", lang, client=client), "")
    app_name = known[client].get("label") or client
    if not st.get("installed"):
        return Check(cid, label, False, i18n.t("doctor.mcp.not_installed", lang, client=app_name, path=st.get("path")),
                     i18n.t("doctor.mcp.not_installed.fix", lang, client=app_name))
    if st.get("station") != sid:
        return Check(cid, label, False, i18n.t("doctor.mcp.wrong_station", lang, got=st.get("station")),
                     i18n.t("doctor.mcp.wrong_station.fix", lang, got=st.get("station"), sid=sid))
    cmd = st.get("command")
    if cmd and (os.sep in cmd or "/" in cmd) and not Path(cmd).exists():
        # exe 文件名带版本号：升级后删了旧 exe，客户端里的条目还指着它
        return Check(cid, label, False, i18n.t("doctor.mcp.cmd_gone", lang, cmd=cmd),
                     i18n.t("doctor.mcp.cmd_gone.fix", lang))
    if cmd and known[client].get("transport") == "http":
        # 0.3 起条目只写网址；旧写法让客户端起一个 exe 子进程，exe 会一直被占着删不掉、换不了
        return Check(cid, label, False, i18n.t("doctor.mcp.old_style", lang, client=client, cmd=cmd),
                     i18n.t("doctor.mcp.old_style.fix", lang, client=app_name))
    return Check(cid, label, True, i18n.t("doctor.mcp.ok", lang, client=app_name), "")


def check_orphans(data_dir: Path | None = None, lang: str | None = None) -> Check:
    """上次盒子没收拾掉的 Pi 进程：父进程已经不在、命令行里还带着本 data 目录。它们会占着 data 删不掉。"""
    from . import procjob
    label = i18n.t("doctor.label.orphans", lang)
    if os.name != "nt":
        return Check("orphans", label, None, i18n.t("doctor.orphans.win_only", lang), "")
    rows = procjob.orphans(Path(data_dir) if data_dir is not None else Path(config.DATA))
    if not rows:
        return Check("orphans", label, True, i18n.t("doctor.orphans.none", lang), "")
    pids = " ".join(str(r["pid"]) for r in rows)
    cmd = " ".join("/PID %s" % r["pid"] for r in rows)
    return Check("orphans", label, False,
                 i18n.t("doctor.orphans.some", lang, n=len(rows), pids=pids),
                 i18n.t("doctor.orphans.some.fix", lang, cmd=cmd))


def check_cursor_enabled(db=None, lang: str | None = None) -> Check:
    """Cursor 按名字记「关掉的 MCP 服务器」。关过一次 boxbox，以后重新登记也还是关着，Cursor 不连，
    首领会话里就看不到 boxbox 的工具。只读 Cursor 的设置库，读不到就跳过。"""
    from . import connectors
    label = i18n.t("doctor.label.cursor", lang)
    off = connectors.cursor_boxbox_disabled(db)
    if off is None:
        return Check("cursor_enabled", label, None, i18n.t("doctor.cursor.unknown", lang), "")
    if not off:
        return Check("cursor_enabled", label, True, i18n.t("doctor.cursor.on", lang), "")
    return Check("cursor_enabled", label, False,
                 i18n.t("doctor.cursor.off", lang),
                 i18n.t("doctor.cursor.off.fix", lang))


def _short(e: object, n: int = 120) -> str:
    s = str(e).replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"


def run(core_url: str | None = None, data_dir=None, stations=None,
        project_dir=None, home=None, leader_client=None, lang: str | None = None) -> list[Check]:
    """跑全套检查。stations 传了就用传的，免得单测落盘 stations.json。
    leader_client 是首领真正连上来的那家 AI 软件（cursor / claude-code / …）；只有它是 Cursor 才查 Cursor 那条。
    lang 给 None 就用当前语言（设置里的 ui_lang）。"""
    try:
        sts = list(stations) if stations is not None else config.stations()
    except Exception:  # noqa: BLE001 - 读工位失败也要出一页，不能空
        sts = []

    def safe(cid: str, label: str, fn, *args) -> Check:
        try:
            return fn(*args)
        except Exception as e:  # noqa: BLE001 - 一项坏掉不能连累整页
            return Check(cid, label, False, i18n.t("doctor.error", lang, why=_short(e)),
                         i18n.t("doctor.error.fix", lang))

    out = []
    if not config.FROZEN:      # exe 里 Python 是打包进来的，用户管不着，这一项不给他看
        out.append(safe("python", i18n.t("doctor.label.python", lang), check_python, lang))
    out.append(safe("data_dir", i18n.t("doctor.label.data_dir", lang), check_data_dir, data_dir, lang))
    out.append(safe("leader", i18n.t("doctor.label.leader", lang), check_leader, sts, lang))
    out.append(safe("core", i18n.t("doctor.label.core", lang), check_core, core_url, 2.0, lang))
    out.append(safe("pi", i18n.t("doctor.label.pi", lang), check_pi, sts, lang))
    for s in sts:
        sid = str(s.get("id") or "")
        if not is_box_run_station(s):     # 盒子自己拉起的工位不用在 AI 软件里连猫猫盒子
            out.append(safe("mcp:%s" % sid, mcp_label(s, lang), check_mcp, s, project_dir, home, lang))
        if s.get("client") == "pi" and s.get("role") != "leader":
            # 首领住在用户自己的 AI 软件里，不用盒子拉起来的密钥（老配置里 client=pi 的首领也按没密钥算）
            out.append(safe("key:%s" % sid, i18n.t("doctor.label.key", lang, sid=sid), check_pi_key, s, lang))
    out.append(safe("templates", i18n.t("doctor.label.templates", lang), check_templates, None, lang))
    out.append(safe("orphans", i18n.t("doctor.label.orphans", lang), check_orphans, data_dir, lang))
    if leader_client == "cursor":        # 首领不是从 Cursor 连上来的，就不查也不显示 Cursor 那条
        out.append(safe("cursor_enabled", i18n.t("doctor.label.cursor", lang), check_cursor_enabled, None, lang))
    return out


def summary(checks: list[Check]) -> dict:
    """三个计数和一个「要不要标红」。"""
    ok = sum(1 for c in checks if c.ok is True)
    fail = sum(1 for c in checks if c.ok is False)
    skip = sum(1 for c in checks if c.ok is None)
    return {"ok": ok, "fail": fail, "skip": skip, "red": fail > 0}


def diagnostics_text(checks: list[Check], extra: dict | None = None, lang: str | None = None) -> str:
    """纯文本诊断信息，给「复制诊断信息」按钮；整体过一遍 mask()。"""
    from . import store

    lines = ["agentboxbox doctor %s" % store.now_iso(),
             "os: %s %s / python: %s" % (platform.system(), platform.release(), platform.python_version())]
    for k, v in (extra or {}).items():
        lines.append("%s: %s" % (k, v))
    for c in checks:
        mark = {True: "[OK]", False: "[FAIL]", None: "[SKIP]"}[c.ok]
        line = "%s %s %s — %s" % (mark, c.id, c.label, c.detail)
        if c.fix:
            line += i18n.t("doctor.fix_suffix", lang, fix=c.fix)
        lines.append(line)
    s = summary(checks)
    lines.append(i18n.t("doctor.summary", lang, ok=s["ok"], fail=s["fail"], skip=s["skip"])
                 + (i18n.t("doctor.summary.red", lang) if s["red"] else ""))
    return mask("\n".join(lines) + "\n")


def mask(text: str) -> str:
    """打码：路径里的用户名换成 ~，密钥样的串换成 ***。不碰环境变量本身。"""
    t = str(text)
    home = str(Path.home())
    for h in (home, home.replace("\\", "/")):
        if h and h not in ("/", "\\"):
            t = t.replace(h, "~")
    t = re.sub(r"(?i)sk-[A-Za-z0-9_-]{6,}", "***", t)
    t = re.sub(r"\bgh[pousr]_[A-Za-z0-9]{6,}", "***", t)
    t = re.sub(r"(?i)\bBearer\s+\S+", "Bearer ***", t)
    t = re.sub(r"(?i)\b(api[_-]?key|token|secret|password)\s*[=:]\s*\S+", r"\1=***", t)
    return t
