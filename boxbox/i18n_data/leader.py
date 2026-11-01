# -*- coding: utf-8 -*-
"""首领那边：工具回话里的规则提醒、事件行、待办提醒。"""
from __future__ import annotations

ZH = {
    "leader.rules": "自己不写代码、不改文件、不跑测试，每件事派卡；用户每说一句先调 get_todo；没调 review 不说做完；"
                    "需求含糊先问；别翻盒子数据目录（里面有密钥）；派完卡用 wait_for_update 等交回，别干等用户来问",
    "leader.http_tips": "PowerShell 先执行 [Console]::OutputEncoding=[Text.Encoding]::UTF8；"
                        "正文里有中文或引号时，先把 JSON 存成 UTF-8 文件再 curl --data-binary @文件 发；"
                        "这种临时文件放 {tmp}、发完删掉，别放进用户的项目目录",
    "leader.mcp_hint": "问用户一次（只问这一次，之后不再提）：要不要把猫猫盒子加进你所在软件的连接设置；"
                       "用户没接话或说不要都算不要。用户同意了，由你自己加：只改你自己这个软件的配置、改前备份、说清改了哪。"
                       "名字 boxbox，类型 HTTP（Streamable HTTP），地址同上。",
    "leader.event.reviewing": "{head} 交回 {tail}，等你验收",
    "leader.event.never_started": "没开工",
    "leader.event.not_run": "没跑成",
    "leader.event.interrupted": "{head} 中断了 {tail}",
    "leader.event.returned": "{head} 打回 {tail}，等你定",
    "leader.event.stuck": "{head} 卡住了 {tail}",
    "leader.event.issue": "{head} 报有问题 {tail}",
    "leader.event.note": "{head} 给你留了言",
    "leader.event.rest_out": "{sid} {word}",
    "leader.event.rest_back": "{sid} 回来了，接着干 {tid}",
    "leader.no_news": "没新消息",
    "leader.event.handoff": "用户把 {n} 张中断的卡交给你决定",
    "leader.event.tail": "{tid}（{title}）",
    "leader.nudge": "{n} 件等你处理，{m} 个工位闲着；调 get_todo 看清单",
    "leader.wait_none": "没新消息",
    "leader.hire.who.leader": "首领",
    "leader.hire.who.member": "打工猫",
    "leader.hire.dispatch": "你自己不动手改文件，活都派卡给打工猫；",
    "leader.hire.line1": "你是猫猫盒子（agentboxbox）的{who}，工位「{sid}」。猫猫盒子是这台电脑上的本地程序，地址 {url}。",
    "leader.hire.line2": "{dispatch}先调 boxbox 的 get_briefing 拿上岗说明，照着做；盒子每次回话里带的提醒也照着做。",
    "leader.hire.line3": "工具里没有 boxbox 的话，按地址用 HTTP 调同样的工具：向上面的地址 POST"
                         "（Content-Type: application/json; charset=utf-8），"
                         "先发 {\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\"}，之后所有 boxbox 工具都这样调。",
    "leader.hire.line4": "地址连不上（拒绝连接）= 猫猫盒子没开：停下来请用户先打开它再继续，"
                         "别去找别的端口或别的目录里的盒子。",
}

EN = {
    "leader.rules": "Do not write code, edit files or run tests yourself; dispatch every job as a card; "
                    "call get_todo whenever the user says anything; never say it is done before calling review; "
                    "ask when the request is vague; do not read the box's data folder (it holds keys); "
                    "after dispatching, wait with wait_for_update instead of waiting for the user",
    "leader.http_tips": "In PowerShell run [Console]::OutputEncoding=[Text.Encoding]::UTF8 first; "
                        "when the body has quotes or non-ASCII text, save the JSON as a UTF-8 file and send it "
                        "with curl --data-binary @file; put such temporary files in {tmp} and delete them afterwards, "
                        "never in the user's project folder",
    "leader.mcp_hint": "Ask the user once (only this once, never again): whether to add agentboxbox to the "
                       "connection settings of your app; if they don't answer or say no, drop it. If the user agrees, add it "
                       "yourself: only change your own app's settings, back them up first, and say what you changed. "
                       "Name: boxbox, type: HTTP (Streamable HTTP), address as above.",
    "leader.event.reviewing": "{head} handed back {tail}, waiting for your review",
    "leader.event.never_started": "never started",
    "leader.event.not_run": "did not run",
    "leader.event.interrupted": "{head} interrupted {tail}",
    "leader.event.returned": "{head} returned {tail}, your call",
    "leader.event.stuck": "{head} is stuck on {tail}",
    "leader.event.issue": "{head} reported a problem with {tail}",
    "leader.event.note": "{head} left you a note",
    "leader.event.rest_out": "{sid} {word}",
    "leader.event.rest_back": "{sid} is back, carrying on with {tid}",
    "leader.no_news": "no new messages",
    "leader.event.handoff": "The user left {n} interrupted cards for you to decide",
    "leader.event.tail": "{tid} ({title})",
    "leader.nudge": "{n} things to handle, {m} stations idle; call get_todo for the list",
    "leader.wait_none": "no new messages",
    "leader.hire.who.leader": "leader",
    "leader.hire.who.member": "worker cat",
    "leader.hire.dispatch": "Do not edit files yourself; dispatch every job as a card to a worker cat. ",
    "leader.hire.line1": "You are the {who} of agentboxbox, station \"{sid}\". "
                         "agentboxbox is a local program on this computer, at {url}.",
    "leader.hire.line2": "{dispatch}First call agentboxbox's get_briefing for the onboarding rules and follow them; "
                         "follow the reminders that come with every reply from the box too.",
    "leader.hire.line3": "If agentboxbox is not in your tool list, call the same tools over HTTP: "
                         "POST to the address above (Content-Type: application/json; charset=utf-8), start with "
                         "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\"}, "
                         "and call every agentboxbox tool that way.",
    "leader.hire.line4": "If the address refuses the connection, agentboxbox isn't running: "
                         "stop and ask the user to open it first, and do not look for another port or another copy "
                         "of the box.",
}
