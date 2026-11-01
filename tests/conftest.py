"""全局测试隔离（#98 之后加的）：测试一律不碰真用户目录。

上岗会给本机认出的客户端（Cursor / Claude Code / Codex）写 MCP 条目，写的是 ~ 下的配置文件；
这里在任何测试 import boxbox 之前，把 HOME / USERPROFILE 指到临时目录，Cursor 设置库指到不存在的路径，
盒子的临时文件目录也指进去（不然测试里派的卡会在程序目录 tmp\\ 下留卡目录）。
Pi 自带模型清单默认不用：测试结果不能跟着这台机器装的 Pi 版本变，要用的测试自己给一份。
测试里起的核心子进程继承这份环境，同样碰不到真目录。

假家目录收尾（发版清单：测试不往 %TEMP% 漏东西）：会话一结束就删，退出时再删一次兜底。
Windows 上文件还被占着的时候一次删不掉，多试几遍再走。
"""
import atexit
import os
import shutil
import tempfile
import time

_FAKE_HOME = tempfile.mkdtemp(prefix="bb-test-home-")
os.environ["USERPROFILE"] = _FAKE_HOME
os.environ["HOME"] = _FAKE_HOME
os.environ["BOXBOX_CURSOR_STATE"] = os.path.join(_FAKE_HOME, "no-cursor", "state.vscdb")
os.environ["BOXBOX_TMP"] = os.path.join(_FAKE_HOME, "boxbox-tmp")
os.environ["BOXBOX_PI_CATALOG"] = "off"

# 界面语言：测试里的断言是老测试写死的中文，所以默认语言定成中文（不然跟着系统语言跑就全红）。
# 要测英文的用例自己把 ui_lang 改成 en（见 tests/ac/test_i18n_all.py）。
# tests/__init__.py 里也定了一份：有些地方用 python -m unittest 跑（不经过这个 conftest）。
from boxbox import config as _config  # noqa: E402

_config.SETTINGS_DEFAULTS["ui_lang"] = "zh"


def _fresh_lang_cache():
    """每个用例前把语言缓存丢掉：测试里数据目录换来换去，缓存不丢会串味。"""
    from boxbox import i18n

    i18n.refresh()


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_lang_cache():
    _fresh_lang_cache()
    yield
    _fresh_lang_cache()


def _clean_fake_home() -> None:
    """删掉假家目录：Windows 上文件被占着的时候一次删不掉，隔一会儿再试。"""
    for _ in range(5):
        if not os.path.isdir(_FAKE_HOME):
            return
        shutil.rmtree(_FAKE_HOME, ignore_errors=True)
        if not os.path.isdir(_FAKE_HOME):
            return
        time.sleep(0.3)


def pytest_sessionfinish(session, exitstatus):
    """一整轮跑完就删假家目录（这时浏览器 / node 都收了，文件不会再被占着）。"""
    _clean_fake_home()


atexit.register(_clean_fake_home)

# 10 个新用户模拟的基准里有打工猫写的 test_*.py（p07 的 test_calc.py），那是产出，不是盒子的测试
collect_ignore_glob = ["personas/*"]
