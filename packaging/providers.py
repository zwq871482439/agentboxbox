# -*- coding: utf-8 -*-
"""生成 boxbox/providers.json：下载 models.dev 的 api.json（约 6 MB，MIT），裁剪后写进包里。

    python packaging/providers.py            # 真联网跑一次，更新包里的快照
    python packaging/providers.py --check    # 只看现在这份快照多大、多新

裁剪逻辑在 boxbox/providers.py（refresh() 更新到 data/ 时用的是同一份），本脚本只管落盘到包里。
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from boxbox import providers  # noqa: E402

SNAPSHOT = ROOT / "boxbox" / "providers.json"


def build() -> dict:
    api = providers.download()
    return providers.trim(api)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--check" in argv:
        snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        n = sum(len(q.get("models") or []) for q in snap.get("providers") or [])
        print("%s：快照日期 %s，%d 家服务商 / %d 个模型，%.2f MB（上限 1.5 MB）"
              % (SNAPSHOT, snap.get("_updated"), len(snap.get("providers") or []), n, SNAPSHOT.stat().st_size / 1e6))
        return 0 if SNAPSHOT.stat().st_size < 1_500_000 else 1
    snap = build()
    SNAPSHOT.write_text(json.dumps(snap, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    n = sum(len(q.get("models") or []) for q in snap["providers"])
    print("已写 %s：%d 家服务商 / %d 个模型，%.2f MB（上限 1.5 MB）"
          % (SNAPSHOT, len(snap["providers"]), n, SNAPSHOT.stat().st_size / 1e6))
    return 0 if SNAPSHOT.stat().st_size < 1_500_000 else 1


if __name__ == "__main__":
    raise SystemExit(main())
