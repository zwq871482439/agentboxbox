# -*- coding: utf-8 -*-
"""首领那边：工具回话里的规则提醒、事件行、待办提醒。"""
from __future__ import annotations

ZH = {
    "leader.rules": "自己不写代码、不改文件、不跑测试，每件事都派给帮手；用户每说一句先调 get_todo；没调 review 不说做完；"
                    "需求含糊先问；别翻盒子数据目录（里面有密钥）；派完用 wait_for_update 等做完，别干等用户来问",
    "leader.http_tips": "PowerShell 先执行 [Console]::OutputEncoding=[Text.Encoding]::UTF8；"
                        "正文里有中文或引号时，先把 JSON 存成 UTF-8 文件再 curl --data-binary @文件 发；"
                        "这种临时文件放 {tmp}、发完删掉，别放进用户的项目目录",
    "leader.mcp_hint": "问用户一次（只问这一次，之后不再提）：要不要把猫猫盒子加进你所在软件的连接设置；"
                       "用户没接话或说不要都算不要。用户同意了，由你自己加：只改你自己这个软件的配置、改前备份、说清改了哪。"
                       "名字 boxbox，类型 HTTP（Streamable HTTP），地址同上。",
    "leader.event.reviewing": "{head} 做完了 {tail}，等你确认",
    "leader.event.never_started": "没开工",
    "leader.event.not_run": "没跑成",
    "leader.event.interrupted": "{head} 中断了 {tail}",
    "leader.event.returned": "{head} 退回重做 {tail}，等你定",
    "leader.event.stuck": "{head} 卡住了 {tail}",
    "leader.event.issue": "{head} 报有问题 {tail}",
    "leader.event.note": "{head} 给你留了言",
    "leader.event.rest_out": "{sid} {word}",
    "leader.event.rest_back": "{sid} 回来了，接着干 {tid}",
    "leader.no_news": "没新消息",
    "leader.wait_capped": "你写了等 {n} 秒，超过上限，这次按 {cap} 秒等。"
                          "上限按 Cursor 收回话的时限留了余地（大约 115 秒）。",
    "leader.event.handoff": "用户把 {n} 个中断的任务交给你决定",
    "leader.event.tail": "{tid}（{title}）",
    "leader.nudge": "{n} 件等你处理，{m} 个帮手闲着；调 get_todo 看清单",
    "leader.hire.who.leader": "编程助手",
    "leader.hire.who.member": "帮手",
    "leader.hire.dispatch": "你自己不动手改文件，活都派给帮手；",
    "leader.hire.line1": "你是猫猫盒子（agentboxbox）的{who}「{sid}」。猫猫盒子是这台电脑上的本地程序，地址 {url}。",
    "leader.hire.line2": "{dispatch}先调 boxbox 的 get_briefing 拿上岗说明，照着做；盒子每次回话里带的提醒也照着做。",
    "leader.hire.line3": "工具里没有 boxbox 的话，按地址用 HTTP 调同样的工具：向上面的地址 POST"
                         "（Content-Type: application/json; charset=utf-8），"
                         "先发 {\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\"}，之后所有 boxbox 工具都这样调。",
    "leader.hire.line4": "地址连不上（拒绝连接）= 猫猫盒子没开：停下来请用户先打开它再继续，"
                         "别去找别的端口或别的目录里的盒子。",
    "leader.event.returned_go": "{head} 退回重做 {tail}，已重派给 {sid}（第 {n} 轮）",
    "leader.event.returned_queued": "{head} 退回重做 {tail}，已排队给 {sid}（第 {n} 轮）",
    "leader.nudge.pending": "还等你处理：{n} 个",
    "leader.nudge.card": "{tid} {kind} {title}",
    "leader.nudge.more": "还有 {n} 个，调 get_todo 看全部",
    "leader.event.half": "{head} {phrase} {tail}",
    "leader.shared": "还有另一个对话也在用「{station}」这个编程助手：待办、做完和确认两边共用。"
                     "要分开，请用户在帮手页再加一个编程助手，把新地址给其中一个对话。",
}

EN = {
    "leader.rules": "Do not write code, edit files or run tests yourself; hand every job to a helper; "
                    "call get_todo whenever the user says anything; never say it is done before calling review; "
                    "ask when the request is vague; do not read the box's data folder (it holds keys); "
                    "after handing off, wait with wait_for_update instead of waiting for the user",
    "leader.http_tips": "In PowerShell run [Console]::OutputEncoding=[Text.Encoding]::UTF8 first; "
                        "when the body has quotes or non-ASCII text, save the JSON as a UTF-8 file and send it "
                        "with curl --data-binary @file; put such temporary files in {tmp} and delete them afterwards, "
                        "never in the user's project folder",
    "leader.mcp_hint": "Ask the user once (only this once, never again): whether to add agentboxbox to the "
                       "connection settings of your app; if they don't answer or say no, drop it. If the user agrees, add it "
                       "yourself: only change your own app's settings, back them up first, and say what you changed. "
                       "Name: boxbox, type: HTTP (Streamable HTTP), address as above.",
    "leader.event.reviewing": "{head} finished {tail}, waiting for your confirmation",
    "leader.event.never_started": "never started",
    "leader.event.not_run": "did not run",
    "leader.event.interrupted": "{head} interrupted {tail}",
    "leader.event.returned": "{head} sent back {tail}, your call",
    "leader.event.stuck": "{head} is stuck on {tail}",
    "leader.event.issue": "{head} reported a problem with {tail}",
    "leader.event.note": "{head} left you a note",
    "leader.event.rest_out": "{sid} {word}",
    "leader.event.rest_back": "{sid} is back, carrying on with {tid}",
    "leader.no_news": "no new messages",
    "leader.wait_capped": "You asked to wait {n} seconds. That is over the cap, so this wait is {cap} seconds. "
                          "The cap leaves room for Cursor to receive the reply (about 115 seconds).",
    "leader.event.handoff": "The user left {n} interrupted tasks for you to decide",
    "leader.event.tail": "{tid} ({title})",
    "leader.nudge": "{n} things to handle, {m} helpers idle; call get_todo for the list",
    "leader.hire.who.leader": "coding assistant",
    "leader.hire.who.member": "helper",
    "leader.hire.dispatch": "Do not edit files yourself; hand every job to a helper. ",
    "leader.hire.line1": "You are agentboxbox's {who}, \"{sid}\". "
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
    "leader.event.returned_go": "{head} sent back {tail}, reassigned to {sid} (round {n})",
    "leader.event.returned_queued": "{head} sent back {tail}, queued for {sid} (round {n})",
    "leader.nudge.pending": "Tasks waiting on you: {n}",
    "leader.nudge.card": "{tid} {kind} {title}",
    "leader.nudge.more": "{n} more; call get_todo for all of them",
    "leader.event.half": "{head} {phrase} {tail}",
    "leader.shared": "Another chat is also using “{station}” as the coding assistant: the to-do list, finished work "
                     "and confirmations are shared. To split them, ask the user to add another coding assistant on the "
                     "Helpers page and give the new address to one of the chats.",
}
