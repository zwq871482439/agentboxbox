"""生成 THIRD_PARTY_LICENSES.txt：exe 里打进去的每一个第三方组件的名字、版本、许可证和许可全文。

    python packaging/licenses.py            # 写仓库根目录的 THIRD_PARTY_LICENSES.txt
    python packaging/licenses.py --check    # 只检查现有文件是不是最新（打包脚本先跑这个）

打进 exe 的东西有四类，都在这里列：
  1. Python 运行时（PSF）和 exe 里的 Python 包：从 BUNDLED_PY 出发，按依赖关系（只取 Windows 上真会装的）展开；
  2. PyInstaller 的启动器（GPL-2.0-or-later + 打包例外）；
  3. pywebview 自带的 Microsoft WebView2 SDK 的几个 DLL；
  4. build/runtime 里的 Node.js 和 Pi，以及 Pi 打包进去的 npm 依赖（按 Pi 全局安装目录下的 node_modules 列）。
另外两份数据 / 样式随仓库分发：models.dev 服务商清单、Tabler CSS。

联网才能拿到的许可全文（Node、Pi、WebView2、models.dev）事先存在 packaging/license_texts/，本脚本不联网。
"""
from __future__ import annotations

import argparse
import importlib.metadata as md
import json
import pathlib
import platform
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "THIRD_PARTY_LICENSES.txt"
TEXTS = ROOT / "packaging" / "license_texts"
BUNDLED_PY = ("pystray", "pywebview", "pillow")          # 打包脚本 pip 装的运行时依赖（见 build_exe.ps1 顶部）
LICENSE_NAMES = re.compile(r"^(LICEN[CS]E|COPYING|NOTICE|AUTHORS)([.-].*)?$", re.I)


def _marker_ok(req: str) -> bool:
    """依赖说明里的环境标记：只留 Windows 上、当前 Python 版本、不带 extra 的。"""
    if ";" not in req:
        return True
    try:
        from packaging.markers import Marker
        return Marker(req.split(";", 1)[1]).evaluate({"extra": ""})
    except ImportError:
        m = req.split(";", 1)[1]
        return "extra" not in m and ("sys_platform" not in m or '"win32"' in m) and "python_version <" not in m


def _req_name(req: str) -> str:
    return re.split(r"[\s;<>=!~\[(]", req.strip(), maxsplit=1)[0]


def python_dists() -> list[md.Distribution]:
    seen, todo, out = set(), list(BUNDLED_PY), []
    while todo:
        name = todo.pop(0)
        key = name.lower().replace("_", "-")
        if key in seen:
            continue
        seen.add(key)
        d = md.distribution(name)
        out.append(d)
        todo += [_req_name(r) for r in (d.requires or []) if _marker_ok(r)]
    return sorted(out, key=lambda d: d.metadata["Name"].lower())


def _dist_license(d: md.Distribution) -> str:
    m = d.metadata
    lic = m.get("License-Expression") or ""
    if not lic:
        lic = (m.get("License") or "").strip().splitlines()[0][:60] if m.get("License") else ""
    if not lic or len(lic) > 40:
        cls = [c.split("::")[-1].strip() for c in (m.get_all("Classifier") or []) if c.startswith("License ::")]
        lic = cls[0] if cls else (lic or "见下方全文")
    return lic


def _dist_texts(d: md.Distribution) -> list[tuple[str, str]]:
    out = []
    for f in d.files or []:
        if LICENSE_NAMES.match(pathlib.PurePath(str(f)).name) and ".dist-info" in str(f):
            try:
                out.append((pathlib.PurePath(str(f)).name, d.locate_file(f).read_text(encoding="utf-8", errors="replace")))
            except OSError:
                pass
    return out


def _mit_stub(holder: str) -> str:
    return ("（这个包的发布文件里没带许可全文；按它声明的 MIT 许可补上标准文本，版权人取自包信息。）\n\n"
            "MIT License\n\nCopyright (c) %s\n\n" % holder + _MIT_BODY)


_MIT_BODY = """Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def _text(name: str) -> str:
    return (TEXTS / name).read_text(encoding="utf-8")


def pi_package_dir() -> pathlib.Path | None:
    npm = shutil.which("npm")
    if not npm:
        return None
    root = subprocess.run([npm, "root", "-g"], capture_output=True, text=True,
                          shell=sys.platform.startswith("win")).stdout.strip()
    p = pathlib.Path(root) / "@earendil-works" / "pi-coding-agent"
    return p if p.is_dir() else None


def npm_packages(pkg_dir: pathlib.Path) -> list[dict]:
    """Pi 安装目录下 node_modules 里的每个包（含嵌套）。"""
    out, seen = [], set()
    for pj in sorted((pkg_dir / "node_modules").rglob("package.json")):
        d = pj.parent
        rel = d.relative_to(pkg_dir / "node_modules").parts
        # 只认包根目录：node_modules/<名字> 或 node_modules/@scope/<名字>（含嵌套的 node_modules）
        names = [i for i, part in enumerate(rel) if part == "node_modules"]
        tail = rel[names[-1] + 1:] if names else rel
        if not (len(tail) == 1 or (len(tail) == 2 and tail[0].startswith("@"))):
            continue
        try:
            meta = json.loads(pj.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        name, ver = meta.get("name"), meta.get("version")
        if not name or not ver or (name, ver) in seen:
            continue
        seen.add((name, ver))
        lic = meta.get("license")
        if isinstance(lic, dict):
            lic = lic.get("type")
        if not lic and isinstance(meta.get("licenses"), list):
            lic = " OR ".join(x.get("type", "?") for x in meta["licenses"] if isinstance(x, dict))
        texts = []
        for f in sorted(d.iterdir()):
            if f.is_file() and LICENSE_NAMES.match(f.name):
                texts.append((f.name, f.read_text(encoding="utf-8", errors="replace")))
        author = meta.get("author")
        if isinstance(author, dict):
            author = author.get("name")
        out.append({"name": name, "version": ver, "license": lic or "（包里没写）", "texts": texts, "author": author})
    return sorted(out, key=lambda x: (x["name"], x["version"]))


def _fill_missing(sections: list) -> None:
    """包里没带全文的：许可证名一样的，借本文件里别的包带的那份全文（Apache-2.0 要求随附许可全文）。
    许可证名没写的，从全文认一下是不是 MIT。"""
    by_lic: dict[str, str] = {}
    for i, (title, lic, use, texts) in enumerate(sections):
        if lic == "见下方全文" and texts and "Permission is hereby granted, free of charge" in texts[0][1]:
            sections[i] = (title, "MIT", use, texts)
    for _title, lic, _use, texts in sections:
        if texts and lic not in by_lic and "（补）" not in texts[0][0]:
            by_lic[lic] = texts[0][1]
    for i, (title, lic, use, texts) in enumerate(sections):
        if not texts and lic in by_lic:
            sections[i] = (title, lic, use, [("%s 标准全文（包里没带，按它声明的许可证补上）" % lic, by_lic[lic])])


def build() -> str:
    from boxbox import __version__
    runtime = json.loads((ROOT / "build" / "runtime" / "versions.json").read_text(encoding="utf-8")) \
        if (ROOT / "build" / "runtime" / "versions.json").exists() else {}
    sections: list[tuple[str, str, str, list[tuple[str, str]]]] = []      # (标题, 许可证, 怎么用, [(文件名, 全文)])

    pyver = platform.python_version()
    py_lic = pathlib.Path(sys.base_prefix) / "LICENSE.txt"
    sections.append(("Python %s" % pyver, "PSF-2.0（另含其中各组件自己的许可）", "exe 里自带的 Python 运行时和标准库",
                     [("LICENSE.txt", py_lic.read_text(encoding="utf-8", errors="replace"))] if py_lic.exists() else []))
    for d in python_dists():
        name, ver = d.metadata["Name"], d.version
        texts = _dist_texts(d)
        lic = _dist_license(d)
        if not texts and "MIT" in lic.upper():
            texts = [("LICENSE（补）", _mit_stub(d.metadata.get("Author") or d.metadata.get("Author-email") or name))]
        use = {"pystray": "托盘图标。LGPL-3.0：见 THIRD_PARTY_NOTICES.md「pystray 和 LGPL」一节",
               "pywebview": "内嵌窗口（同时带了下面 Microsoft WebView2 SDK 的 DLL）",
               "pillow": "画托盘图标"}.get(name.lower(), "上面几个包的依赖")
        sections.append(("%s %s" % (name, ver), lic, use, texts))
    pyi = md.distribution("pyinstaller")
    sections.append(("PyInstaller 启动器 %s" % pyi.version, "GPL-2.0-or-later，带打包例外（允许用任何许可分发打出来的 exe）",
                     "exe 外壳：启动时把程序解压到临时目录再运行", _dist_texts(pyi)))
    sections.append(("Microsoft WebView2 SDK 1.0.3856.49", "BSD-3-Clause（Microsoft）",
                     "pywebview 自带的 Microsoft.Web.WebView2.Core.dll / WinForms.dll / WebView2Loader.dll；"
                     "WebView2 运行时本身是 Windows 组件，不在 exe 里",
                     [("LICENSE.txt", _text("Microsoft.Web.WebView2-1.0.3856.49-LICENSE.txt")),
                      ("NOTICE.txt", _text("Microsoft.Web.WebView2-1.0.3856.49-NOTICE.txt"))]))
    node_ver = runtime.get("node", "")
    sections.append(("Node.js %s" % node_ver, "MIT（另含其中各组件自己的许可）", "exe 里自带的 node.exe，用来跑 Pi",
                     [("LICENSE", _text("node-v24.13.0-LICENSE.txt"))]))
    sections.append(("@earendil-works/pi-coding-agent %s" % runtime.get("pi", ""), "MIT", "exe 里自带的 Pi（打工猫干活用的命令行 agent）",
                     [("LICENSE", _text("pi-coding-agent-LICENSE.txt"))]))
    pi_dir = pi_package_dir()
    npm = npm_packages(pi_dir) if pi_dir else []
    for p in npm:
        texts = p["texts"]
        if not texts and "MIT" in str(p["license"]).upper():
            texts = [("LICENSE（补）", _mit_stub(p["author"] or p["name"] + " authors"))]
        sections.append(("%s %s" % (p["name"], p["version"]), str(p["license"]), "Pi 打包进去的 npm 依赖", texts))
    _fill_missing(sections)
    sections.append(("models.dev 服务商清单", "MIT", "boxbox/providers.json（裁剪过的快照）",
                     [("LICENSE", _text("models.dev-LICENSE.txt"))]))
    tab = ROOT / "static" / "tabler" / "LICENSE"
    sections.append(("Tabler CSS 1.6.1", "MIT", "static/tabler/tabler.min.css（只有 CSS）",
                     [("LICENSE", tab.read_text(encoding="utf-8"))] if tab.exists() else []))

    lines = ["agentboxbox %s 第三方许可全文 / Third-party license texts" % __version__,
             "由 packaging/licenses.py 生成，不要手改。agentboxbox 自己的代码是 MIT 许可，见 LICENSE。",
             "说明和合规要点（尤其是 pystray 的 LGPL-3.0）见 THIRD_PARTY_NOTICES.md。", "",
             "== 目录（共 %d 项）==" % len(sections)]
    for title, lic, use, _ in sections:
        lines.append("- %s — %s — %s" % (title, lic, use))
    missing = [t for t, _, _, texts in sections if not texts]
    if missing:
        lines += ["", "下面这些包的发布文件里没有许可全文，许可证名按它们自己的声明写在目录里：", *("  " + m for m in missing)]
    for title, lic, use, texts in sections:
        lines += ["", "=" * 78, "%s" % title, "许可证：%s" % lic, "用途：%s" % use, "=" * 78]
        for fname, body in texts:
            lines += ["", "--- %s ---" % fname, body.rstrip()]
    return "\n".join(lines) + "\n"


def verify_toc(toc_path: pathlib.Path) -> list[str]:
    """打完包核对：exe 里实际收进去的非标准库 Python 包，都要在许可清单里。返回漏掉的包名。"""
    toc = toc_path.read_text(encoding="utf-8")
    mods = set(re.findall(r"\('([A-Za-z0-9_]+)(?:\.[A-Za-z0-9_.]+)?',\s*'[^']*',\s*'PYMODULE'\)", toc))
    listed = {d.metadata["Name"].lower() for d in python_dists()}
    pkg2dist = md.packages_distributions()
    missing = []
    for m in sorted(mods):
        if m in sys.stdlib_module_names or m.startswith("_") or m == "boxbox":
            continue
        dists = [d.lower() for d in pkg2dist.get(m, [m])]
        if not any(d in listed for d in dists):
            missing.append("%s（%s）" % (m, ",".join(dists)))
    return missing


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只检查 THIRD_PARTY_LICENSES.txt 是不是最新")
    ap.add_argument("--verify-toc", help="打完包核对 PYZ-00.toc：exe 里的 Python 包都要在许可清单里")
    a = ap.parse_args()
    sys.path.insert(0, str(ROOT))
    if a.verify_toc:
        miss = verify_toc(pathlib.Path(a.verify_toc))
        if miss:
            print("exe 里有许可清单没列的 Python 包（要么在 build_exe.ps1 里 --exclude-module，要么加进 BUNDLED_PY）：")
            print("\n".join("  " + m for m in miss))
            return 1
        print("exe 里的 Python 包都在许可清单里")
        return 0
    text = build()
    if a.check:
        cur = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if cur != text:
            print("THIRD_PARTY_LICENSES.txt 不是最新：先跑 python packaging/licenses.py 再提交")
            return 1
        print("THIRD_PARTY_LICENSES.txt 是最新的")
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print("写好了 %s（%.0f KB）" % (OUT, OUT.stat().st_size / 1024))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
