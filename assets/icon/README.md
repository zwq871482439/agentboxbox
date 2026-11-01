# boxbox 图标

来源：Grok Bot 生成，方案 A（像素风纸箱里探出一只小猫，深蓝圆角方底）。
原图是 `source-a.jpg`（1024 方形 JPG，带白边）。其余文件都由 `make_icons.py` 生成：裁掉白边，圆角方以外透明。

重新生成：`python assets/icon/make_icons.py`（需要 Pillow）。

| 文件 | 用途 |
|---|---|
| `icon-1024.png` `icon-512.png` | 母版、商店/大图展示 |
| `icon-256.png` `icon-128.png` | 文档、关于页、大图标 |
| `icon-192.png` | 网页 `<link rel=icon type=image/png>`、PWA |
| `icon-64.png` `icon-48.png` `icon-32.png` `icon-16.png` | 托盘、列表等小图标（16/32 做过面积平均 + 轻锐化） |
| `favicon.ico` | 网页 favicon（16/32/48），`/favicon.ico` 路由提供 |
| `apple-touch-icon.png` | iOS 主屏图标（180），`/apple-touch-icon.png` 路由提供 |
| `boxbox.ico` | 安装包、exe 和托盘图标（16/24/32/48/64/128/256） |
| `make_icons.py` | 生成以上全部文件的脚本 |

网页路由：`dashboard.py` 和 `python -m boxbox serve` 都提供 `/favicon.ico`、`/apple-touch-icon.png` 和 `/assets/icon/<文件名>`。
