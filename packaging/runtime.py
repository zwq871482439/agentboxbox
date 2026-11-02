"""把 Node 运行时和 Pi 一起打进 exe：在 build/runtime/ 里摆好
    node.exe
    pi/            <- @earendil-works/pi-coding-agent 的 dist/bundle（已打包好依赖，单独能跑）
    versions.json  <- {"node": "v24.x", "pi": "1.4.0"}
build_exe.ps1 再用 --add-data 把整个目录放进 exe 的 runtime/。核心运行时由 pi_config.runtime() 优先用它。

Pi 的版本钉死在 PI_VERSION：服务商的新模型要 Pi 认得（比如哪个模型必须开自适应思考），
打包机上全局装的是哪个版本都不算数。全局装的正好是这个版本就直接用，不是就用 npm pack 取一份到 build/ 里，
不动打包机全局装的 Pi。

    python packaging/runtime.py [out_dir]     # 默认 build/runtime
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tarfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
PI_PKG = ("@earendil-works", "pi-coding-agent")
PI_VERSION = "1.4.0"
IS_WIN = sys.platform.startswith("win")


def find_node() -> pathlib.Path:
    n = shutil.which("node")
    if not n:
        raise SystemExit("打包机上找不到 node：先装 Node.js（运行时要从这里拷 node.exe）")
    return pathlib.Path(n).resolve()


def _npm() -> str:
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("打包机上找不到 npm")
    return npm


def _version(pkg: pathlib.Path) -> str | None:
    try:
        return json.loads((pkg / "package.json").read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError):
        return None


def _global_pkg() -> pathlib.Path | None:
    # 子进程输出在英文 Windows 上是 cp1252，这里按 UTF-8 解，免得中文/符号变成乱码
    root = subprocess.run([_npm(), "root", "-g"], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", shell=IS_WIN).stdout.strip()
    p = pathlib.Path(root).joinpath(*PI_PKG) if root else None
    return p if p and (p / "dist" / "bundle" / "cli.js").is_file() else None


def fetch_pi(version: str = PI_VERSION) -> pathlib.Path:
    """npm pack 取这个版本的 Pi，解到 build/pi-<版本>/package；已经解过就直接用。"""
    dest = ROOT / "build" / ("pi-" + version)
    pkg = dest / "package"
    if (pkg / "dist" / "bundle" / "cli.js").is_file() and _version(pkg) == version:
        return pkg
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    spec = "%s/%s@%s" % (PI_PKG[0], PI_PKG[1], version)
    r = subprocess.run([_npm(), "pack", spec, "--silent", "--pack-destination", str(dest)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", shell=IS_WIN)
    tgz = next(iter(sorted(dest.glob("*.tgz"))), None)
    if r.returncode != 0 or tgz is None:
        raise SystemExit("取不到 Pi %s：%s" % (version, (r.stderr or r.stdout).strip()[:300]))
    with tarfile.open(tgz) as tf:
        tf.extractall(dest, filter="data")
    tgz.unlink()
    if _version(pkg) != version:
        raise SystemExit("解出来的 Pi 版本不对：%s" % _version(pkg))
    return pkg


def find_pi_pkg(version: str = PI_VERSION) -> pathlib.Path:
    g = _global_pkg()
    if g is not None and _version(g) == version:
        return g
    return fetch_pi(version)


def stage(out: pathlib.Path, node: pathlib.Path, pi_pkg: pathlib.Path) -> dict:
    """把 node 和 pi 的 bundle 拷进 out（先清空）。返回 versions。"""
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copy2(node, out / node.name)
    shutil.copytree(pi_pkg / "dist" / "bundle", out / "pi")
    shutil.copy2(pi_pkg / "package.json", out / "pi" / "package.json")   # Pi 从这里读自己的版本号（没有就报 0.0.0）
    node_ver = subprocess.run([str(node), "--version"], capture_output=True, text=True,
                              encoding="utf-8", errors="replace").stdout.strip()
    versions = {"node": node_ver, "pi": _version(pi_pkg)}
    (out / "versions.json").write_text(json.dumps(versions), encoding="utf-8")
    return versions


if __name__ == "__main__":
    # 打包机是英文 Windows，输出编码是 cp1252，中文一打就崩；脚本自己把输出改成 UTF-8
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build" / "runtime"
    v = stage(out, find_node(), find_pi_pkg())
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print("runtime staged: %s  node %s  pi %s  (%.1f MB)" % (out, v["node"], v["pi"], size / 1048576))
