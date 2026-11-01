"""服务商清单：models.dev 的快照，登记 Pi 工位时选服务商 / 模型、按公开单价估算花费。

- 快照由 packaging/providers.py 生成，提交在 boxbox/providers.json（裁剪到 1 MB 以内，MIT）。
- load() 优先读 data/providers.json（用户在设置页点「更新」下载的），没有再读包里的快照。
- refresh() 要联网：不带 confirm 只说明要下载什么，带了才真下载（和自检修复一个原则）。
- 模型在快照里存成数组省体积，字段顺序见 MODEL_FIELDS；load() 展开成字典。

仅标准库。不打印、不读环境变量。"""
from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
import threading
import urllib.parse
import urllib.request

from . import config, i18n

URL = "https://models.dev/api.json"
SOURCE = "models.dev"
#: 联网更新前给用户看的说明（要告诉用户下载什么、存到哪里）
# 下载前的确认文字按当下的语言给（设置页会展示）

#: 快照里每个模型数组的字段顺序（packaging/providers.py 生成时按这个顺序裁剪）
MODEL_FIELDS = ("id", "name", "context", "output", "cost_input", "cost_output",
                "cost_cache_read", "cost_cache_write", "tool_call", "reasoning")

#: npm 包名 → Pi 的接口类型（models.dev 每家给 npm 字段；其它 openai 兼容包都走 openai-completions）
_NPM_API = {
    "@ai-sdk/anthropic": "anthropic-messages",
    "@ai-sdk/openai-compatible": "openai-completions",
    "@ai-sdk/openai": "openai-responses",
    "@ai-sdk/google": "google-generative-ai",
}

_PKG_FILE = pathlib.Path(__file__).with_name("providers.json")
_COST_KEYS = ("input", "output", "cache_read", "cache_write")

_CACHE: dict = {}          # {"sig": (path, mtime, size), "doc": {...}, "index": {...}}
_CACHE_LOCK = threading.Lock()


def _short(e: object, n: int = 160) -> str:
    s = str(e).replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"


def _num(v):
    """快照里尽量存整数、少存小数位；解析不了的值原样丢弃（None）。"""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v) if float(v).is_integer() else float(v)
    try:
        f = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return int(f) if f.is_integer() else f


def trim(api: dict, updated: str | None = None) -> dict:
    """把 models.dev 的 api.json 裁成快照：服务商留 id/name/api/env/npm，
    模型留 id/name/limit.context/limit.output/cost 四项/tool_call/reasoning。
    没有 api 地址的服务商也留着（用户可以手填地址）。"""
    out = []
    for pid, p in (api or {}).items():
        if not isinstance(p, dict):
            continue
        q: dict = {"id": str(p.get("id") or pid), "name": str(p.get("name") or pid)}
        if p.get("api"):
            q["api"] = str(p["api"])
        if p.get("npm"):
            q["npm"] = str(p["npm"])
        if isinstance(p.get("env"), list) and p.get("env"):
            q["env"] = [str(e) for e in p["env"] if e]
        models = []
        for mid, m in (p.get("models") or {}).items():
            if not isinstance(m, dict):
                continue
            lim = m.get("limit") if isinstance(m.get("limit"), dict) else {}
            cost = m.get("cost") if isinstance(m.get("cost"), dict) else {}
            models.append([str(m.get("id") or mid), str(m.get("name") or mid),
                           _num(lim.get("context")), _num(lim.get("output")),
                           _num(cost.get("input")), _num(cost.get("output")),
                           _num(cost.get("cache_read")), _num(cost.get("cache_write")),
                           bool(m.get("tool_call")), bool(m.get("reasoning"))])
        q["models"] = models
        out.append(q)
    out.sort(key=lambda q: q["id"])
    return {"_updated": updated or _dt.date.today().isoformat(), "_source": SOURCE, "providers": out}


def _save(path: pathlib.Path, snap: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(snap, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


def download(url: str = URL, timeout_s: float = 90.0) -> dict:
    """下载 models.dev 的 api.json（约 6 MB）。"""
    req = urllib.request.Request(url, headers={"User-Agent": "agentboxbox/%s" % _version()})  # noqa: S310 - https 固定地址
    with urllib.request.urlopen(req, timeout=timeout_s) as r:
        return json.loads(r.read().decode("utf-8"))


def _version() -> str:
    from . import __version__
    return __version__


def _pick_file() -> tuple[pathlib.Path, str]:
    """先 data/providers.json（用户更新过的），没有再包里的快照。返回 (路径, 来源)。"""
    data = config.DATA / "providers.json"
    if data.is_file():
        return data, "data"
    if _PKG_FILE.is_file():
        return _PKG_FILE, "snapshot"
    return data, "none"


def _expand(snap: dict) -> tuple[dict, dict]:
    """快照 → {provider_id: {..., models: [模型字典]}}，外加 {provider_id: {model_id: 模型}} 索引。"""
    doc: dict = {}
    index: dict = {}
    for q in snap.get("providers") or []:
        pid = str(q.get("id") or "")
        if not pid:
            continue
        p = {"id": pid, "name": str(q.get("name") or pid), "api": q.get("api"),
             "env": list(q.get("env") or []), "npm": str(q.get("npm") or ""), "models": []}
        midx: dict = {}
        for row in q.get("models") or []:
            if not isinstance(row, list) or len(row) < len(MODEL_FIELDS):
                continue
            m = {"id": str(row[0]), "name": str(row[1]), "context": row[2], "output": row[3],
                 "cost": {"input": row[4], "output": row[5], "cache_read": row[6], "cache_write": row[7]},
                 "tool_call": bool(row[8]), "reasoning": bool(row[9])}
            p["models"].append(m)
            midx[m["id"]] = m
        doc[pid] = p
        index[pid] = midx
    return doc, index


def _read(path: pathlib.Path):
    try:
        st = path.stat()
    except OSError:
        return None
    try:
        return path, (st.st_mtime_ns, st.st_size), json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _loaded() -> tuple[dict, dict, str]:
    """(providers 字典, 模型索引, 来源)，带 mtime 缓存。"""
    path, source = _pick_file()
    with _CACHE_LOCK:
        hit = _CACHE.get("sig")
        got = _read(path)
        if got is None:
            return {}, {}, source
        path, sig, snap = got
        if hit is None or hit[0] != str(path) or hit[1] != sig:
            doc, index = _expand(snap)
            _CACHE["sig"] = (str(path), sig)
            _CACHE["doc"], _CACHE["index"], _CACHE["meta"] = doc, index, snap.get("_updated")
        return _CACHE["doc"], _CACHE["index"], source


def load() -> dict:
    """{provider_id: 服务商字典}。用户更新过的 data/providers.json 优先，没有再包里的快照。"""
    return _loaded()[0]


def meta() -> dict:
    """清单用的哪份、什么时候的：source ∈ data（已更新）/ snapshot（自带快照）/ none。"""
    doc, _, source = _loaded()
    with _CACHE_LOCK:
        updated = _CACHE.get("meta")
    models = sum(len(p.get("models") or []) for p in doc.values())
    return {"source": source, "updated": updated, "providers": len(doc), "models": models}


def api_type(npm: str) -> str:
    """npm 包名 → Pi 的接口类型；不认识的 openai 兼容包默认 openai-completions。"""
    return _NPM_API.get(str(npm or ""), "openai-completions")


# ---- 服务商是谁 ----
def station_provider(st: dict) -> str | None:
    """工位的服务商 key：pi 块里的 provider_id 优先；没记就按 base_url 的主机名算。不是 Pi 工位 → None。"""
    pi = (st or {}).get("pi") or {}
    if not pi:
        return None
    pid = str(pi.get("provider_id") or "").strip()
    if pid:
        return pid
    raw = str(pi.get("base_url") or "").strip()
    host = ""
    try:
        host = urllib.parse.urlparse(raw).hostname or ""
    except ValueError:
        host = ""
    if not host and raw:
        head = raw.split("/", 1)[0]              # 没写协议的地址：第一个 / 前面那截当主机名
        if ":" in head:
            port = head.rsplit(":", 1)[1]
            head = head.rsplit(":", 1)[0] if port.isdigit() else head
        host = head
    host = host.lower().strip()
    return host or None


def price(provider_id: str, model_id: str) -> dict | None:
    """每百万 token 美元单价 {input, output, cache_read, cache_write}；找不到或没标价 → None（价格 0 是有效值，套餐模型常见）。"""
    _, index, _ = _loaded()
    m = (index.get(str(provider_id or "")) or {}).get(str(model_id or ""))
    if not m:
        return None
    c = m.get("cost") or {}
    if all(c.get(k) is None for k in _COST_KEYS):
        return None
    out = {}
    for k in _COST_KEYS:
        try:
            out[k] = float(c[k]) if c.get(k) is not None else 0.0
        except (TypeError, ValueError):
            out[k] = 0.0
    return out


def match(host: str, model_id: str) -> tuple[str, str] | None:
    """按接口地址主机名 + 模型 id 在清单里找（工位没记 provider_id 时的兜底）。"""
    if not host or not model_id:
        return None
    doc, _, _ = _loaded()
    for pid, p in doc.items():
        api = p.get("api")
        if not api:
            continue
        try:
            if (urllib.parse.urlparse(api).hostname or "") != str(host):
                continue
        except ValueError:
            continue
        if any(m.get("id") == model_id for m in p.get("models") or []):
            return pid, str(model_id)
    return None


def list_doc() -> dict:
    """/api/providers 的返回：精简列表（服务商 + 模型，含接口地址、key 环境变量名、上下文长度、价格）。"""
    doc, _, source = _loaded()
    with _CACHE_LOCK:
        updated = _CACHE.get("meta")
    out = []
    for pid in sorted(doc):
        p = doc[pid]
        kind = api_type(p.get("npm"))
        url = p.get("api")
        if url and kind == "anthropic-messages" and str(url).rstrip("/").lower().endswith("/v1"):
            url = str(url).rstrip("/")[:-3]       # 清单按 AI SDK 的写法带 /v1；Pi 的 Anthropic 接口自己补 /v1，表单里填不带的
        out.append({"id": pid, "name": p["name"], "api": url, "env": p.get("env") or [],
                    "npm": p.get("npm") or "", "api_type": kind,
                    "models": p.get("models") or []})
    return {"source": source, "updated": updated, "providers": out}


def refresh(confirm: bool = False, url: str = URL, timeout_s: float = 90.0) -> dict:
    """更新服务商清单（设置页「更新」按钮）。不带 confirm 只说明要下载什么，不联网。"""
    if not confirm:
        return {"ok": False, "needs_confirm": True, "text": i18n.t("app.providers.need_confirm")}
    try:
        snap = trim(download(url, timeout_s))
        path = config.DATA / "providers.json"
        _save(path, snap)
    except (OSError, ValueError) as e:
        return {"ok": False, "error_kind": i18n.t("app.providers.network"),
                "text": i18n.t("app.providers.failed", err=_short(e))}
    m = meta()
    return {"ok": True, "source": m["source"], "updated": m["updated"], "providers": m["providers"], "models": m["models"],
            "text": i18n.t("app.providers.done", n=m["providers"], m=m["models"], path=path)}
