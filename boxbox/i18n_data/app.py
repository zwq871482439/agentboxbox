# -*- coding: utf-8 -*-
"""核心自己的提示：启动、端口占用、退出。"""
from __future__ import annotations

ZH = {
    "list.sep": "、",
    "app.secrets_note": "secrets.json 里是明文的 API key，只给这台机器上的 boxbox 用。\n"
                        "别把 data/ 目录拷给别人；要换密钥到设置页改。\n",
    "app.core_already": "端口 {port} 上已经有一个猫猫盒子在跑；直接打开 http://127.0.0.1:{port}/ 即可，不用再起一个",
    "app.port_busy": "端口 {port} 被占用（{why}）；换个端口：boxbox serve --port 8879，或在设置里改 core_port",
    "app.core_started": "猫猫盒子启动了（端口 {port}）",
    "app.core_stopped": "猫猫盒子停了",
    "app.reset.stop_cards": "中断在跑的卡",
    "app.reset.clear_stations": "清空工位和设置",
    "app.reset.clear_keys": "清掉 API key",
    "app.reset.clear_tasks": "清空任务记录",
    "app.reset.clear_files": "清空日志和卡片文件",
    "app.providers.need_confirm": "要从 models.dev 下载最新的服务商清单（约 6 MB），存到 data/providers.json",
    "app.providers.failed": "下载或保存失败：{err}",
    "app.providers.network": "网络问题",
    "app.providers.done": "已下载并裁剪：{n} 家服务商 / {m} 个模型，存到 {path}",
}

EN = {
    "list.sep": ", ",
    "app.secrets_note": "The API keys in secrets.json are plain text, for agentboxbox on this computer only.\n"
                        "Do not copy the data/ folder to anyone else; change a key on the Settings page.\n",
    "app.core_already": "Another agentboxbox is already running on port {port}; just open http://127.0.0.1:{port}/, no need to start one more",
    "app.port_busy": "Port {port} is taken ({why}); use another port: boxbox serve --port 8879, or change core_port in data/settings.json",
    "app.core_started": "agentboxbox started (port {port})",
    "app.core_stopped": "agentboxbox stopped",
    "app.reset.stop_cards": "interrupt the running cards",
    "app.reset.clear_stations": "clear the stations and the settings",
    "app.reset.clear_keys": "clear the API keys",
    "app.reset.clear_tasks": "clear the task history",
    "app.reset.clear_files": "clear the logs and the card files",
    "app.providers.need_confirm": "download the latest provider list from models.dev (about 6 MB) into data/providers.json",
    "app.providers.failed": "the download or the save failed: {err}",
    "app.providers.network": "network problem",
    "app.providers.done": "downloaded and trimmed: {n} providers / {m} models, saved to {path}",
}
