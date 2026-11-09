# 第三方声明 / Third-party notices

agentboxbox 自己的代码是 MIT 许可（见 [LICENSE](LICENSE)）。这份文件说明：仓库和 exe 里带了哪些别人的东西、各自什么许可、我们怎么遵守。每个组件的**许可全文**在 [THIRD_PARTY_LICENSES.txt](THIRD_PARTY_LICENSES.txt)（由 `packaging/licenses.py` 生成，打包时会核对 exe 里的东西和这份清单一致）。exe 的设置页「许可和隐私」里也能打开这几份文件。

## 仓库里自己的美术和素材

- **像素猫、办公室、道具、上岗动画**（`office/`、`assets/chibicat/`、`assets/design/`）：本仓库原创，全部由代码在画布上绘制（`office/office.html`、`office/build/cats.js`），按 MIT 许可随代码一起分发。办公室早中晚的背景也是画布代码画的，不是外部图片。
- **应用图标**（`assets/icon/`）：用 Grok（xAI）生成后由维护者挑选、再用 `make_icons.py` 裁切，使用遵守 xAI 的服务条款。我们在自己享有的权利范围内按 MIT 许可提供。
- **宣传短片**（`assets/promo/`）：画面由脚本逐帧绘制，配乐由 `make_music.py` 用 numpy 合成。字幕渲染时用了 Noto Sans CJK SC（SIL Open Font License 1.1），仓库里不带字体文件。
- **截图**（`office/screenshots/`、`office/mockups/`）：都是本软件自己的界面。

## 随仓库分发的第三方文件

| 文件 | 来源 | 许可 |
|---|---|---|
| `static/tabler/tabler.min.css` | Tabler 1.6.1（基于 Bootstrap） | MIT，全文 `static/tabler/LICENSE`，文件头注释保留 |
| `boxbox/providers.json` | models.dev（`sst/models.dev`）公开清单的裁剪快照 | MIT |

## 打进 exe 里的第三方组件

exe 是 PyInstaller 打的单文件包，里面带了下面这些（版本以 THIRD_PARTY_LICENSES.txt 为准）：

| 组件 | 许可 | 用途 |
|---|---|---|
| Python 运行时和标准库 | PSF-2.0 | 运行 agentboxbox |
| pywebview、pythonnet、clr_loader、bottle、proxy_tools、cffi、pycparser、typing_extensions | BSD-3-Clause / MIT / PSF-2.0 | 内嵌窗口 |
| Microsoft WebView2 SDK 的 DLL（pywebview 自带） | BSD-3-Clause（Microsoft） | 内嵌窗口；WebView2 运行时本身是 Windows 组件，不在 exe 里 |
| pystray | **LGPL-3.0** | 托盘图标，见下一节 |
| Pillow、six | MIT-CMU / MIT | 画托盘图标 |
| PyInstaller 启动器 | GPL-2.0-or-later，带打包例外 | exe 外壳。这个例外明确允许用任何许可分发打出来的程序 |
| Node.js | MIT（含其中各组件的许可） | 运行 Pi |
| Pi（`@earendil-works/pi-coding-agent`）及它打包进去的 npm 依赖 | MIT，依赖里有 Apache-2.0、BSD-3-Clause、ISC、BlueOak-1.0.0、0BSD、Unlicense | 打工猫干活用的命令行 agent |

这些许可都允许再分发，条件是附上版权声明和许可全文——THIRD_PARTY_LICENSES.txt 就是做这件事的，exe 里也带着它。我们没有修改上面任何一个组件的源码。

### pystray 和 LGPL-3.0

pystray 是唯一的 LGPL 组件。我们这样遵守：

- exe 里附带了 LGPL-3.0 和 GPL-3.0 全文（THIRD_PARTY_LICENSES.txt 的 pystray 一节）。
- 我们没有改 pystray，用的是 PyPI 上的原版（版本见 THIRD_PARTY_LICENSES.txt），源码在 <https://github.com/moses-palmer/pystray> 和 PyPI 上都能拿到。
- agentboxbox 的完整源码和打包脚本（`packaging/build_exe.ps1`）都是公开的。你可以换一个改过的 pystray，按 README「开发」一节重新打出 exe，这就是 LGPL 要求的「能用修改过的库重新组合」。

## 不打包、你自己装的东西

agentboxbox 会调用或读写下面这些，但不带它们：AI 客户端（Cursor、Claude Code、Codex、Kimi Code、MiniMax Code、Grok Bot、WorkBuddy、ZCode）、Git（只执行 `git` 命令读提交记录）、你选的模型服务商的接口。它们各自的许可和服务条款由你和它们之间约定。

## 名称和商标

Cursor、Claude、Codex、Kimi、GLM / 智谱、MiniMax、Grok、WorkBuddy、ZCode、Pi、GitHub、Windows、Microsoft Edge 等名称属于各自的所有者。这里提到它们只是为了说明 agentboxbox 能和哪些软件、服务配合使用，不代表与它们有关联或得到它们的认可。

---

agentboxbox's own code is MIT-licensed. Full license texts for everything bundled in the exe are in `THIRD_PARTY_LICENSES.txt`. The pixel art, office scenes and animations are original and drawn by code in this repository; the app icon was generated with Grok (xAI) and is offered under MIT to the extent we hold rights in it. pystray (LGPL-3.0) is used unmodified; since the complete source and build script of agentboxbox are public, you can rebuild the exe with a modified pystray. All product names belong to their owners; no affiliation or endorsement is implied.
