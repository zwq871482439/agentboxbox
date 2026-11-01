"""Pi 自带的模型清单：每家服务商、每个模型，Pi 自己是怎么接的（接口类型、地址、兼容开关、思考档位）。

工位填的接口地址 / 模型对得上 Pi 自带的那一条，写 models.json 时就照 Pi 的设置来——Pi 怎么接，猫就怎么接。
服务商新出的模型 Pi 还没收录、接口回话里又写明了要什么（比如「requires adaptive thinking」），
就把这一条兼容开关记进工位的 pi.compat，下次照着发。
清单向打包进来的 Pi 现问（node 跑一小段脚本），按 Pi 版本缓存在 data/pi/catalog.json。
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import threading
import time

from . import config, tmpdir

# 只取写 models.json 用得上的字段
_FIELDS = ("provider", "id", "api", "baseUrl", "reasoning", "input", "compat", "thinkingLevelMap", "contextWindow", "maxTokens")
_APIS = ("anthropic-messages", "openai-completions", "openai-responses", "google-generative-ai")

_JS = r"""
import { pathToFileURL } from "node:url";
import { mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
const pi = await import(pathToFileURL(process.argv[2]).href);
const dir = mkdtempSync(join(process.argv[3], "pi-catalog-"));
try {
  const rt = await pi.ModelRuntime.create({ modelsPath: null, authPath: join(dir, "auth.json") });
  const keep = JSON.parse(process.argv[4]);
  const out = rt.getAllModels().map((m) => Object.fromEntries(keep.filter((k) => m[k] !== undefined).map((k) => [k, m[k]])));
  process.stdout.write(JSON.stringify(out));
} finally {
  rmSync(dir, { recursive: true, force: true });
}
"""

# 接口回话里写明要的兼容开关：（认这句话的正则, 要打开的 Pi compat 字段, 给人看的说法的词条）
HEALS = (
    (re.compile(r"requires adaptive thinking", re.I), "forceAdaptiveThinking", "compat.adaptive"),
    (re.compile(r"reasoning_content[^\n]{0,60}(missing|required|must)", re.I), "requiresReasoningContentOnAssistantMessages",
     "compat.reasoning_content"),
)

_LOCK = threading.Lock()
_MEM: dict = {}            # {"key": 版本键, "models": [...]}
_FAILED_AT = {"t": 0.0}    # 现问失败过：10 分钟内别再每次都起 node
RETRY_AFTER_S = 600.0


def _runtime() -> dict:
    from . import pi_config  # pi_config 写 models.json 时要用这里，这里只在用到时取运行时
    return pi_config.runtime()


def _key(rt: dict) -> str:
    cli = str(rt.get("cli") or "")
    try:
        stamp = int(os.path.getmtime(cli))
    except OSError:
        stamp = 0
    return "%s|%s|%d" % (rt.get("pi_version") or "", cli, stamp)


def _cache_file() -> pathlib.Path:
    return config.DATA / "pi" / "catalog.json"


def _ask_pi(rt: dict, timeout_s: float) -> list[dict] | None:
    """让打包进来的 Pi 自己报一遍清单。不成功返回 None。"""
    cli = pathlib.Path(str(rt.get("cli") or ""))
    index = cli.parent / "index.js"
    if not rt.get("node") or not index.is_file():
        return None
    work = tmpdir.root()
    work.mkdir(parents=True, exist_ok=True)
    script = work / "pi-catalog.mjs"
    script.write_text(_JS, encoding="utf-8")
    env = dict(os.environ, PI_OFFLINE="1", PI_TELEMETRY="0", PI_SKIP_VERSION_CHECK="1", PI_CODING_AGENT_DIR=str(work / "pi-catalog-home"))
    try:
        r = subprocess.run([str(rt["node"]), str(script), str(index), str(work), json.dumps(list(_FIELDS))],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout_s, env=env,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        doc = json.loads(r.stdout) if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        doc = None
    finally:
        try:
            script.unlink()
        except OSError:
            pass
        shutil.rmtree(work / "pi-catalog-home", ignore_errors=True)
    if not isinstance(doc, list):
        return None
    return [m for m in doc if isinstance(m, dict) and m.get("api") in _APIS and m.get("id") and m.get("baseUrl")]


def load(timeout_s: float = 30.0) -> list[dict]:
    """Pi 自带的全部模型（只留四种接口的）。没有 Pi / 现问失败 → 空列表，写 models.json 时就不照 Pi 的来。
    环境变量 BOXBOX_PI_CATALOG：off = 不用清单；指一个 JSON 文件 = 用这份（测试用）。"""
    forced = os.environ.get("BOXBOX_PI_CATALOG", "")
    if forced == "off":
        return []
    if forced:
        try:
            return json.loads(pathlib.Path(forced).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
    rt = _runtime()
    if not rt.get("cli"):
        return []
    key = _key(rt)
    with _LOCK:
        if _MEM.get("key") == key:
            return _MEM["models"]
        try:
            doc = json.loads(_cache_file().read_text(encoding="utf-8"))
            if doc.get("key") == key and isinstance(doc.get("models"), list):
                _MEM.update(key=key, models=doc["models"])
                return doc["models"]
        except (OSError, ValueError, AttributeError):
            pass
        if _FAILED_AT["t"] and time.monotonic() - _FAILED_AT["t"] < RETRY_AFTER_S:
            return []
        models = _ask_pi(rt, timeout_s)
        if models is None:
            _FAILED_AT["t"] = time.monotonic()
            return []
        _MEM.update(key=key, models=models)
        try:
            f = _cache_file()
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".json.tmp")
            tmp.write_text(json.dumps({"key": key, "models": models}, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, f)
        except OSError:
            pass
        return models


def base_url(url: str, api: str) -> str:
    """Pi 认的接口地址写法：去掉末尾的 /；Anthropic 那种接口 Pi 自己会补 /v1/messages，地址末尾的 /v1 要去掉，
    不然请求发到 /v1/v1/messages（服务商清单里不少写的是带 /v1 的）。"""
    u = str(url or "").strip().rstrip("/")
    if api == "anthropic-messages" and u.lower().endswith("/v1"):
        u = u[:-3]
    return u


def _same_url(a: str, b: str) -> bool:
    return a.rstrip("/").lower() == b.rstrip("/").lower()


def _related(station_provider: str, pi_provider: str) -> bool:
    """服务商清单里的 id 和 Pi 的 id 是不是同一家（minimax-cn-coding-plan ↔ minimax-cn）。"""
    a, b = str(station_provider or "").lower(), str(pi_provider or "").lower()
    return bool(a and b) and (a == b or a.startswith(b + "-") or b.startswith(a + "-"))


def _common_compat(models: list[dict]) -> dict:
    """同一个地址下所有模型都一样的兼容开关（各模型自己的不算）。"""
    out: dict | None = None
    for m in models:
        c = m.get("compat") or {}
        out = dict(c) if out is None else {k: v for k, v in out.items() if c.get(k) == v}
    return out or {}


def resolve(pi: dict, catalog: list[dict] | None = None) -> dict:
    """工位的 pi 块对上 Pi 自带的哪一条：返回写 models.json 用的 {api, baseUrl, compat?, thinkingLevelMap?, reasoning?, input?, match}。
    match：model = 地址和模型都对上；endpoint = 只对上地址（用这个地址下所有模型都一样的兼容开关）；空 = 没对上。"""
    pi = pi or {}
    models = load() if catalog is None else catalog
    api = str(pi.get("api") or "")
    url = base_url(pi.get("base_url") or "", api)
    mid = str(pi.get("model") or "").casefold()
    at_url = [m for m in models if _same_url(base_url(m["baseUrl"], m["api"]), url) or _same_url(m["baseUrl"], pi.get("base_url") or "")]
    apis = {m["api"] for m in at_url}
    if at_url and api not in apis and len(apis) == 1:
        api = apis.pop()                 # 这个地址 Pi 用的是另一种接口：照 Pi 的
        url = base_url(pi.get("base_url") or "", api)
    same = [m for m in at_url if m["api"] == api]
    hit = next((m for m in same if str(m["id"]).casefold() == mid), None)
    if hit is None and mid:
        hit = next((m for m in models if m["api"] == api and str(m["id"]).casefold() == mid
                    and _related(pi.get("provider_id"), m.get("provider"))), None)
    out: dict = {"api": api, "baseUrl": url, "match": ""}
    if hit is not None:
        out["match"] = "model"
        for k in ("compat", "thinkingLevelMap", "reasoning", "input"):
            if hit.get(k) is not None:
                out[k] = hit[k]
    elif same:
        out["match"] = "endpoint"
        common = _common_compat(same)
        if common:
            out["compat"] = common
    return out


def heal_for(text: str) -> tuple[str, str] | None:
    """接口回话里写明了要哪个兼容开关 → （Pi compat 字段, 给人看的说法的词条）；没有 → None。"""
    for rx, field, label in HEALS:
        if text and rx.search(text):
            return field, label
    return None


def apply_heal(station_id: str, text: str) -> str | None:
    """按接口回话把兼容开关记进工位的 pi.compat。真改了返回说法的词条；没认出来或已经开着返回 None。"""
    fix = heal_for(text)
    if fix is None:
        return None
    field, label = fix
    items = config.stations()
    for st in items:
        if st.get("id") != station_id or not isinstance(st.get("pi"), dict):
            continue
        compat = dict(st["pi"].get("compat") or {})
        if compat.get(field) is True:
            return None
        compat[field] = True
        st["pi"] = dict(st["pi"], compat=compat)
        config.save_stations(items)
        return label
    return None


def keep_compat(old: dict | None, new: dict) -> dict:
    """工位重新保存（改名字、换样子）时，接口地址和模型没变就留着之前自动打开的兼容开关。"""
    old_pi, new_pi = (old or {}).get("pi") or {}, new.get("pi")
    if not isinstance(new_pi, dict) or "compat" in new_pi or not old_pi.get("compat"):
        return new
    if old_pi.get("base_url") != new_pi.get("base_url") or old_pi.get("model") != new_pi.get("model"):
        return new
    return dict(new, pi=dict(new_pi, compat=old_pi["compat"]))
