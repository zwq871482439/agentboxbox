"""打包用的版本信息：exe 文件名和 Windows「属性 → 详细信息」里的版本都从 boxbox.__version__ 来。

    python packaging/version_info.py name              # 打印 exe 文件名，如 agentboxbox_0.3.0.exe
    python packaging/version_info.py file <out.txt>    # 写 PyInstaller 的 --version-file
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRODUCT = "agentboxbox"


def version() -> str:
    text = (ROOT / "boxbox" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)


def exe_stem(ver: str | None = None) -> str:
    """agentboxbox_<版本号>；开发版也带上 .devN，一眼能看出不是正式版。"""
    return "agentboxbox_%s" % (ver or version())


def file_tuple(ver: str) -> tuple[int, int, int, int]:
    """'0.3.0.dev2' -> (0, 3, 0, 2)；Windows 文件版本只能是四个数。"""
    nums = [int(x) for x in re.findall(r"\d+", ver)][:4]
    return tuple(nums + [0] * (4 - len(nums)))  # type: ignore[return-value]


def version_file_text(ver: str | None = None) -> str:
    ver = ver or version()
    t = file_tuple(ver)
    return """VSVersionInfo(
  ffi=FixedFileInfo(filevers=%(t)r, prodvers=%(t)r, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('080404b0', [
      StringStruct('CompanyName', '%(p)s'),
      StringStruct('FileDescription', '%(p)s 猫猫盒子'),
      StringStruct('FileVersion', '%(v)s'),
      StringStruct('InternalName', '%(stem)s'),
      StringStruct('OriginalFilename', '%(stem)s.exe'),
      StringStruct('ProductName', '%(p)s'),
      StringStruct('ProductVersion', '%(v)s')])]),
    VarFileInfo([VarStruct('Translation', [0x0804, 1200])])
  ]
)
""" % {"t": t, "v": ver, "p": PRODUCT, "stem": exe_stem(ver)}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "name"
    if cmd == "name":
        print(exe_stem())
    elif cmd == "file":
        out = pathlib.Path(sys.argv[2])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(version_file_text(), encoding="utf-8")
        print(out)
    else:
        sys.exit("usage: version_info.py name | file <out>")
