# -*- coding: utf-8 -*-
"""猫猫配饰系统的规则半边：招募随机外观 + 工位 look 清洗。

画画的另一半在 office/build/cats.js（槽位表两边要保持一致，规则见 assets/chibicat/onboard/README.md）。

规则：
- 槽位 head（crown / cap / beanie / flower / bow）、face（glasses / sunglasses）、
  neck（scarf / bell / tie / bandana）、ears（phones）、body（hoodie）；每个槽位最多一件，同槽位互斥。
- 招募时随机 0–3 件；随机永远不出王冠。
- 王冠只给首领：谁当首领，头部槽位换成王冠（原来的头部配饰摘掉，其它槽位保留）；
  不是首领的猫，look 里写了 crown 也摘掉。
- 快递帽（送货期间盖掉头部槽位，含王冠）是画布上的临时状态，不落进工位配置。
"""
from __future__ import annotations

SLOTS = {
    "head": ("crown", "cap", "beanie", "flower", "bow"),
    "face": ("glasses", "sunglasses"),
    "neck": ("scarf", "bell", "tie", "bandana"),
    "ears": ("phones",),
    "body": ("hoodie",),
}
ACC_SLOT = {a: s for s, names in SLOTS.items() for a in names}
CAT_COUNT = 8        # 底猫 8 只：1..6 原有 + 7 虎斑（棕）+ 8 奶牛猫（黑白）


def random_look(rng, lead: bool = False, used=None) -> dict:
    """招募时的随机外观：{"cat": 1..8, "acc": {槽位: 配饰}}。
    配饰 0–3 件、同槽位不重复、永远不出王冠（lead=True 时由首领规则补上王冠）。
    rng 是 random.Random 之类的对象（要有 randint / sample / choice），固定种子结果固定。
    used：别的工位已经在用的底猫号，只从还没用的号里挑；8 只都用过了才允许重复。"""
    n = rng.randint(0, 3)
    slots = rng.sample(sorted(SLOTS), k=min(n, len(SLOTS)))
    acc = {s: rng.choice([a for a in SLOTS[s] if a != "crown"]) for s in slots}
    taken = {c for c in (used or ()) if isinstance(c, int)}
    free = [c for c in range(1, CAT_COUNT + 1) if c not in taken]
    cat = rng.choice(free) if free else rng.randint(1, CAT_COUNT)
    return normalize({"cat": cat, "acc": acc}, lead)


def normalize(look, lead: bool = False) -> dict | None:
    """清洗一份工位 look：不认识的槽位 / 配饰丢掉，同槽位只留一件（先来先得），王冠只给首领。

    look 不是 dict、cat 不在 1..8 时返回 None（调用方按「没有 look」处理）。
    acc 可以是 {槽位: 配饰名}，也可以是一串配饰名（同槽位重复时先来先得）。"""
    if not isinstance(look, dict):
        return None
    try:
        cat = int(look.get("cat"))
    except (TypeError, ValueError):
        return None
    if not 1 <= cat <= CAT_COUNT:
        return None
    raw = look.get("acc")
    acc: dict = {}
    if isinstance(raw, dict):
        for s in SLOTS:                     # 按固定槽位顺序走，结果稳定
            v = raw.get(s)
            if isinstance(v, str) and v in SLOTS[s]:
                acc[s] = v
    elif isinstance(raw, (list, tuple)):
        for v in raw:
            s = ACC_SLOT.get(v)
            if s and s not in acc:
                acc[s] = v
    if lead:
        acc["head"] = "crown"               # 谁当首领，头部槽位换成王冠（原头部配饰摘掉）
    elif acc.get("head") == "crown":
        del acc["head"]                     # 王冠只给首领
    return {"cat": cat, "acc": acc}
