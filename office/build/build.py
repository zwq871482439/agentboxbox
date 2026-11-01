# -*- coding: utf-8 -*-
"""把 office.src.html 骨架 + src/ 源文件 + art/ 像素数据拼成 ../office.html。
src/ 的拼接顺序固定（见 SRC_ORDER）；art/ 的像素数据拼成同名的 JS 常量。
改了 src/ 或 art/ 之后重新跑 python build/build.py。"""
import json
import os
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / "src"
ART = HERE / "art"

# src/ 的拼接顺序：01 常量工具 → … → 19 启动（art_props.js 在 16 聚会前）
SRC_ORDER = [
    "01_i18n.js", "01_core.js", "02_data.js", "03_canvas.js", "04_skin.js", "05_layout.js",
    "06_actor.js", "07_scene_frame.js", "08_meet_scene.js", "09_draw_room.js",
    "10_overlay.js", "11_onboard_anim.js", "12_loop.js", "13_interact.js",
    "14_topbar.js", "15_demo.js", "art_props.js", "16_party.js", "17_switch.js",
    "18_invite.js", "19_boot.js",
]


def js_str_rows(rows):
    """像素行数组 → JS 数组字面量（一行一个字符串）。"""
    return "[" + ",".join(json.dumps(r, ensure_ascii=False) for r in rows) + "]"


def js_quote(s):
    return json.dumps(s, ensure_ascii=False)


def load_frames(path):
    """pixel_*.txt：段首 frame=<键>，其后一行一个像素行 → {键: [行,...]}。"""
    frames = {}
    cur = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("frame="):
            cur = line[6:]
            frames[cur] = []
        elif line == "":
            cur = None
        elif cur is not None:
            frames[cur].append(line)
    return frames


def load_art_pr(path):
    """art_*.txt：开头若干行 pal 键=色，其后一行一个像素行 → {p:{...}, r:[...]}。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    pal = {}
    rows = []
    for line in lines:
        if line.startswith("pal "):
            k, v = line[4:].split("=", 1)
            pal[k] = v
        elif line:
            rows.append(line)
    return {"p": pal, "r": rows}


def art_js():
    """art/ 数据 → 一段 JS：常量名和原来内联在代码里的一模一样。"""
    out = ["/* ==== 像素立绘 / 调色板（由 build.py 从 art/ 数据文件生成，别手改） ==== */"]

    # 调色板：房色 / 天空 / 小调色板，直接 dumps 整个 dict
    tables = json.loads((ART / "palette_tables.json").read_text(encoding="utf-8"))
    pals = json.loads((ART / "palettes.json").read_text(encoding="utf-8"))
    for name, val in tables.items():
        out.append("const %s=%s;" % (name, json.dumps(val, ensure_ascii=False, separators=(",", ":"))))
    for name, val in pals.items():
        out.append("const %s=%s;" % (name, json.dumps(val, ensure_ascii=False, separators=(",", ":"))))

    # {键:[像素行]} 形立绘（每键一行，跟原来内联时一个排版）
    for js_name, fname in [
        ("ARCADE_ART", "pixel_arcade_art.txt"), ("MENU_ART", "pixel_menu_art.txt"),
        ("MODE_ART", "pixel_mode_art.txt"), ("DOT_ART", "pixel_dot_art.txt"),
        ("PMELEM", "pixel_pmelem.txt"), ("SLOT_LETTER", "pixel_slot_letter.txt"),
        ("ICON", "pixel_icon.txt"), ("MICON", "pixel_micon.txt"),
        ("SWITCH_ART", "pixel_switch_art.txt"),
    ]:
        frames = load_frames(ART / fname)
        if "*" in frames:                     # 数组形（DOT_ART）
            out.append("const %s=%s;" % (js_name, js_str_rows(frames["*"])))
        else:
            body = ",\n".join(" %s:%s" % (k, js_str_rows(v)) for k, v in frames.items())
            out.append("const %s={\n%s};" % (js_name, body))

    # {feed:{idle:[...]}} 两层形（BTN_ART）
    frames = load_frames(ART / "pixel_btn_art.txt")
    groups = {}
    for key, rows in frames.items():
        top, sub = key.split(".", 1)
        groups.setdefault(top, []).append((sub, rows))
    body = ",".join("%s:{%s}" % (top, ",".join("%s:%s" % (s, js_str_rows(r)) for s, r in subs))
                    for top, subs in groups.items())
    out.append("const BTN_ART={%s};" % body)

    # {p:{...}, r:[...]} 形（DONG / BOX）
    for js_name, fname in [
        ("DONG_ART", "art_dong_art.txt"), ("DONG_ART_EN", "art_dong_art_en.txt"),
        ("BOX_CLOSED", "art_box_closed.txt"), ("BOX_OPEN", "art_box_open.txt"),
        ("BOX_PARCEL", "art_box_parcel.txt"),
    ]:
        val = load_art_pr(ART / fname)
        out.append("const %s={p:%s,r:%s};" % (js_name,
                    json.dumps(val["p"], ensure_ascii=False, separators=(",", ":")),
                    js_str_rows(val["r"])))
    return "\n".join(out) + "\n"


def main():
    os.chdir(HERE)
    src = open("office.src.html", encoding="utf-8").read()
    sample = json.dumps(json.load(open("../sample.json", encoding="utf-8")), ensure_ascii=False)
    cats = open("cats.js", encoding="utf-8").read()

    css = (SRC / "style.css").read_text(encoding="utf-8")
    body = (SRC / "body.html").read_text(encoding="utf-8")
    parts = [art_js()]                                   # 像素数据在最前（常量先定义）
    for name in SRC_ORDER:
        text = (SRC / name).read_text(encoding="utf-8")
        text = text.replace("__CATS_JS__", cats)         # 03_canvas.js 里的猫精灵整段
        parts.append(text)

    out = (src.replace("__CSS__", css)
              .replace("__BODY__", body)
              .replace("__SAMPLE__", sample.replace("</", "<\\/"))
              .replace("__SCRIPTS__", "\n".join(parts)))
    open("../office.html", "w", encoding="utf-8").write(out)
    print("built", len(out))


if __name__ == "__main__":
    main()
