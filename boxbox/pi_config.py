"""Pi 配置目录生成：核心自有 data/pi/（models.json + settings.json），不再依赖用户 ~/.pi。

用户在 onboarding 填接口地址 / API 类型 / 模型 id / 上下文窗口 / 最大输出，
这里据此生成 Pi 能直接用的 models.json。apiKey 只写 "$BOXBOX_KEY_..." 引用，文件里永不出现密钥明文；
密钥本身只存 data/secrets.json，Pi 进程启动时由 pi_env() 注入。
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import socket
import sys
import threading
import time
import urllib.parse
from typing import NamedTuple

from . import config, i18n, pi_catalog

APIS = ("anthropic-messages", "openai-completions", "openai-responses", "google-generative-ai")
SCHEMA = "https://pi.dev/schemas/models.schema.json"


def provider_name(station_id: str) -> str:
    """工位 id -> provider 名。纯 ASCII：小写、非字母数字换 '-'；含非 ASCII：utf-8 十六进制前 8 位。"""
    sid = str(station_id or "")
    if not sid.isascii():
        return "boxbox-" + sid.encode("utf-8").hex()[:8]
    slug = re.sub(r"[^a-z0-9]+", "-", sid.lower()).strip("-")
    return "boxbox-" + (slug or sid.encode("utf-8").hex()[:8])


def validate_pi_block(pi: dict, lang: str | None = None) -> list[str]:
    """校验工位的 pi 块，返回错误列表；空列表 = 合法。"""
    lg = lang or i18n.lang()
    errs: list[str] = []
    if not isinstance(pi, dict):
        return [i18n.t("pi.not_object", lg)]
    for key in ("base_url", "api", "model"):
        if not pi.get(key):
            errs.append(i18n.t("pi.missing", lg, key=key))
    api = pi.get("api")
    if api and api not in APIS:
        errs.append(i18n.t("pi.api_bad", lg, v=repr(api), list=" / ".join(APIS)))
    for key in ("context_window", "max_tokens"):
        v = pi.get(key)
        if v is None:
            continue
        if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
            errs.append(i18n.t("pi.int_bad", lg, key=key, v=repr(v)))
    if pi.get("compat") is not None and not isinstance(pi.get("compat"), dict):
        errs.append(i18n.t("pi.compat_bad", lg))
    return errs


def host_of(pi: dict) -> str:
    """从 base_url 解析主机名（给 TCP 预检用）。"""
    try:
        return urllib.parse.urlparse(str((pi or {}).get("base_url", ""))).hostname or ""
    except ValueError:
        return ""


# ---- 接口探测（所有 client=pi 的工位都探） ----
def host_port(pi: dict, default_port: int = 443) -> tuple[str, int]:
    """接口地址里的（主机, 端口）。写不出主机 -> ("", 默认端口)。"""
    pi = pi or {}
    raw = str(pi.get("base_url") or "").strip()
    host, port = "", default_port
    if raw:
        try:
            u = urllib.parse.urlparse(raw if "://" in raw else "//" + raw)
            host = (u.hostname or "").lower()
            port = u.port or (80 if u.scheme == "http" else default_port)
        except ValueError:
            host, port = "", default_port
        if not host:                                # 没写协议的地址：/ 前面那截当主机[:端口]
            head = raw.split("/", 1)[0]
            if ":" in head:
                hp = head.rsplit(":", 1)
                if hp[1].isdigit():
                    head, port = hp[0], int(hp[1])
            host = head.lower()
    return host or "", int(port or default_port)


#: 探测一次接口的规矩：DNS 最多 3 秒、连接 3 秒；试 3 次、两次隔 0.5 秒
DNS_TIMEOUT_S = 3.0
CONNECT_TIMEOUT_S = 3.0
PROBE_TRIES = 3
PROBE_RETRY_GAP_S = 0.5


class ProbeResult(NamedTuple):
    """一次接口探测的结果：通没通、花了多少毫秒、卡在哪一步、解析到的地址。"""
    ok: bool
    ms: int
    stage: str      # ""（通）/ "dns" / "connect" / "timeout"
    addr: str      # 解析到的 IP；没解析出来是空串


def _resolve(host: str, port: int, budget_s: float) -> list[str]:
    """DNS 解析：最多 budget_s 秒；解析不出来或解析超时都返回空列表。

    解析放在独立线程里跑：域名服务器不回的时候，不能让整个探测一直挂着。
    """
    box: dict = {}

    def work():
        try:
            box["info"] = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
        except (OSError, UnicodeError) as e:
            box["err"] = e

    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(budget_s)
    if th.is_alive() or "err" in box:
        return []
    ips: list[str] = []
    for _fam, _typ, _proto, _cn, sa in box.get("info", []):
        ip = str(sa[0])
        if ip and ip not in ips:
            ips.append(ip)
    return ips


def api_probe(pi: dict, timeout_s: float = CONNECT_TIMEOUT_S, dns_timeout_s: float = DNS_TIMEOUT_S) -> ProbeResult:
    """开工前探一次接口地址：先 DNS 解析、再 TCP 连接，两步分开计时。

    总超时把 DNS 算进去：解析最多 dns_timeout_s 秒、连接最多 timeout_s 秒，
    DNS 慢不会挤掉连接那份余量，探测一共花的毫秒里也含 DNS 那段。
    最多试 PROBE_TRIES 次、两次隔 PROBE_RETRY_GAP_S 秒，任一次连上就算通。
    写不出主机 -> 通（没地址就不拦）。返回 (通没通, 一共花的毫秒, 卡在哪一步, 解析到的 IP)。"""
    host, port = host_port(pi)
    if not host:
        return ProbeResult(True, 0, "", "")
    t0 = time.monotonic()
    stage, addr = "", ""
    for i in range(PROBE_TRIES):
        ips = _resolve(host, int(port), dns_timeout_s)
        if not ips:
            stage = "dns"                      # 没解析出来（解析失败或解析超时）：卡在 DNS
        else:
            for ip in ips:
                addr = ip
                try:
                    with socket.create_connection((ip, int(port)), timeout=timeout_s):
                        return ProbeResult(True, int((time.monotonic() - t0) * 1000), "", addr)
                except socket.timeout:          # 连接超时
                    stage = "timeout"
                except OSError:                # 拒了 / 够不着
                    stage = "connect"
        if i < PROBE_TRIES - 1:
            time.sleep(PROBE_RETRY_GAP_S)
    return ProbeResult(False, int((time.monotonic() - t0) * 1000), stage, addr)


def api_reachable(pi: dict, timeout_s: float = CONNECT_TIMEOUT_S) -> bool:
    """api_probe 的布尔版（重试节奏原样保留：三次、隔 0.5 秒，任一次连上就算通）。"""
    return api_probe(pi, timeout_s).ok


#: api_reachable 的别名，老代码还按这个名字调
intranet_reachable = api_reachable


def build_models_json(stations: list[dict], catalog: list[dict] | None = None) -> dict:
    """client=="pi" 且 enabled 的工位每站一个 provider；校验不过的跳过，错误进 "_skipped"（不写文件）。
    地址和模型对得上 Pi 自带的那一条，接口类型、兼容开关、思考档位、能不能看图都照 Pi 的写（见 pi_catalog）；
    上下文长度和最大输出用工位上填的；工位 pi.compat 里记的开关最后盖上去。"""
    providers: dict = {}
    skipped: dict[str, list[str]] = {}
    for st in stations or []:
        if st.get("client") != "pi" or not st.get("enabled", True):
            continue
        sid = str(st.get("id", ""))
        pi = st.get("pi") or {}
        errs = validate_pi_block(pi)
        if errs:
            skipped[sid] = errs
            continue
        known = pi_catalog.resolve(pi, catalog)
        model: dict = {"id": pi["model"]}
        if pi.get("context_window"):
            model["contextWindow"] = pi["context_window"]
        if pi.get("max_tokens"):
            model["maxTokens"] = pi["max_tokens"]
        if known.get("reasoning") is not None:
            model["reasoning"] = bool(known["reasoning"])      # Pi 认得这个模型：会不会思考听 Pi 的
        elif pi.get("reasoning") is not None:
            model["reasoning"] = bool(pi.get("reasoning"))
        for k in ("thinkingLevelMap", "input"):
            if known.get(k):
                model[k] = known[k]
        compat = dict(known.get("compat") or {})
        compat.update(pi.get("compat") or {})
        if compat:
            model["compat"] = compat
        providers[provider_name(sid)] = {
            "baseUrl": known["baseUrl"],
            "api": known["api"],
            "apiKey": "$" + key_env_name(sid),
            "models": [model],
        }
    doc: dict = {"$schema": SCHEMA, "providers": providers}
    if skipped:
        doc["_skipped"] = skipped
    return doc


def write_pi_dir(stations: list[dict], pi_dir: pathlib.Path | None = None) -> pathlib.Path:
    """建目录、原子写 models.json（去掉 _skipped）、补 settings.json；返回目录路径。"""
    d = pathlib.Path(pi_dir) if pi_dir else config.DATA / "pi"
    d.mkdir(parents=True, exist_ok=True)
    doc = build_models_json(stations)
    doc.pop("_skipped", None)
    target = d / "models.json"
    tmp = target.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    os.replace(tmp, target)
    settings = d / "settings.json"
    if not settings.exists():
        with open(settings, "w", encoding="utf-8") as f:
            json.dump({"telemetry": False}, f, ensure_ascii=False, indent=2)
    return d


def key_env_name(station_id: str) -> str:
    """Pi 读密钥用的环境变量名：盒子自己的名字 BOXBOX_KEY_<工位>，pi_env() 用 data/secrets.json 里的密钥填它。
    名字是盒子内部约定的，用户系统里同名的变量一律不算数（密钥只认 secrets.json）。"""
    return "BOXBOX_KEY_" + provider_name(station_id)[len("boxbox-"):].upper().replace("-", "_")


def key_available(station: dict) -> bool:
    """这个工位有没有密钥：只看 data/secrets.json 里存的那一份。"""
    return bool(config.get_secret(str((station or {}).get("id") or "")))


def pi_env(station: dict, base_env: dict | None = None) -> dict:
    """给 Pi 子进程的环境：复制 base_env，加 PI_CODING_AGENT_DIR 等；
    密钥只从 data/secrets.json 来：存了就写进盒子自己的变量名，没存就把这个名字从环境里删掉
    （不能顺手捡用户系统里同名的变量当密钥用）。"""
    env = dict(os.environ if base_env is None else base_env)
    env["PI_CODING_AGENT_DIR"] = str(config.DATA / "pi")
    env["PI_SKIP_VERSION_CHECK"] = "1"
    env["PI_TELEMETRY"] = "0"                      # 隐私声明：Pi 的安装统计、版本检查、启动时的联网都关掉
    env["PI_OFFLINE"] = "1"                        # 只关「启动时的联网」，不影响调模型
    env["PYTHONIOENCODING"] = "utf-8"
    extra_ca = env.get("NODE_EXTRA_CA_CERTS")
    if extra_ca and not os.path.isfile(extra_ca):
        env.pop("NODE_EXTRA_CA_CERTS")             # 指向不存在的证书文件（别的软件留下的）：Node 每次都打一句警告，没用
    sid = str((station or {}).get("id") or "")
    name = key_env_name(sid)
    stored = config.get_secret(sid)
    if stored:
        env[name] = stored
    else:
        env.pop(name, None)
    return env


def _find_cli_js() -> str | None:
    """cli.js 位置：Windows 看 %APPDATA%\\npm\\...；否则从 PATH 上的 pi 推导。"""
    appdata = os.environ.get("APPDATA")
    if appdata:
        p = pathlib.Path(appdata) / "npm" / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "bundle" / "cli.js"
        if p.exists():
            return str(p)
    pi = shutil.which("pi")
    if pi:
        # <...>/npm/pi(.cmd) -> <...>/npm/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js
        p = pathlib.Path(pi).resolve().parent / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "bundle" / "cli.js"
        if p.exists():
            return str(p)
    return None


def bundled_dir() -> pathlib.Path | None:
    """exe 自带的运行时目录：打包时把 node.exe 和 pi 的 dist/bundle 放进 runtime/。
    exe 里在 sys._MEIPASS/runtime；跑源码时可以用 BOXBOX_RUNTIME 指一个同样结构的目录（测试 / 开发用）。"""
    cands = []
    if os.environ.get("BOXBOX_RUNTIME"):
        cands.append(pathlib.Path(os.environ["BOXBOX_RUNTIME"]))
    mei = getattr(sys, "_MEIPASS", None)
    if mei:
        cands.append(pathlib.Path(mei) / "runtime")
    for d in cands:
        if (d / "pi" / "cli.js").is_file() and (d / ("node.exe" if os.name == "nt" else "node")).is_file():
            return d
    return None


def runtime() -> dict:
    """用哪套 Node + Pi：自带的优先，没有再用系统里装的。
    返回 {node, cli, source: bundled|system|None, pi_version, node_version}；找不到的字段是 None。"""
    d = bundled_dir()
    if d is not None:
        info = {}
        try:
            info = json.loads((d / "versions.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        return {"node": str(d / ("node.exe" if os.name == "nt" else "node")), "cli": str(d / "pi" / "cli.js"),
                "source": "bundled", "pi_version": info.get("pi"), "node_version": info.get("node")}
    node, cli = shutil.which("node"), _find_cli_js()
    pi_ver = None
    if cli:
        try:  # <pkg>/dist/bundle/cli.js -> <pkg>/package.json
            pi_ver = json.loads((pathlib.Path(cli).parent.parent.parent / "package.json").read_text(encoding="utf-8")).get("version")
        except (OSError, ValueError):
            pass
    return {"node": node, "cli": cli, "source": "system" if node and cli else None, "pi_version": pi_ver, "node_version": None}


def pi_cli_argv(station: dict, prompt: str, session_dir: pathlib.Path, continue_session: bool = False) -> list[str]:
    """[node, cli.js, --mode json, --provider <名>, --model <id>, --session-dir <dir>, prompt]。没装 Pi 抛 FileNotFoundError。
    --no-skills / --no-prompt-templates：不加载用户本机 ~/.agents 里的 skills 和提示模板（隐私 + 省 token + 免干扰）；
    --no-context-files 不加：项目里的 AGENTS.md 对打工猫有用。
    continue_session=True：命令行加 --continue —— 接着这个 session 目录里上次那段对话往下做
    （Pi 的 --continue = 接着这个目录里最近的一次会话）。"""
    rt = runtime()
    node, cli = rt["node"], rt["cli"]
    if not node or not cli:
        raise FileNotFoundError(i18n.t("pi.not_found"))
    pi = (station or {}).get("pi") or {}
    argv = [node, cli, "--mode", "json", "--no-skills", "--no-prompt-templates",
            "--provider", provider_name(str(station.get("id", ""))),
            "--model", str(pi.get("model", "")),
            "--session-dir", str(session_dir)]
    if continue_session:
        argv.append("--continue")
    argv.append(prompt)
    return argv
