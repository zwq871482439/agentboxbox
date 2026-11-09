# -*- coding: utf-8 -*-
"""客户端工具通道里给模型看的话：工具说明、参数说明、连接提示。"""
from __future__ import annotations

ZH = {
    "mcp.get_briefing": "新会话第一条：返回你的角色、规则、可用工具和当前看板摘要。",
    "mcp.get_board": "每个工位一行：状态词、在做哪张卡、分钟。只读。",
    "mcp.get_todo": "首领的待办：待验收、卡住、打回待定、失败、闲着的工位。按谁在等排序。",
    "mcp.get_task": "看一张任务卡的全部：卡、状态、轮次、运行、token、回报。member 只能看自己的卡。",
    "mcp.assign": "首领派一张自包含的任务卡给某个工位（打工猫）。卡里各字段见 card 的说明；"
                  "缺 goal / inputs / expected_output / acceptance.review 会直接拒收并告诉你缺什么。返回送达回执；不重试。",
    "mcp.assign.station": "派给哪个工位（打工猫的名字，get_board 里看）",
    "mcp.assign.title": "一句话标题，看板上显示",
    "mcp.assign.goal": "要什么、做到什么程度。卡要自包含：打工猫是新会话，看不到你和用户的对话",
    "mcp.assign.cwd": "打工猫在哪个目录干活（绝对路径）。要读写用户项目里的文件，就写那个项目的绝对路径"
                      "（通常就是你当前的工作目录）；不写的话打工猫在它自己的空目录里干，看不到用户的文件。"
                      "写了的目录必须已经存在，不然这张卡直接被拒收",
    "mcp.assign.inputs": "要读的文件（相对 cwd）。空目录、没有现成文件可读时写 [\"（无，新建）\"]",
    "mcp.assign.expected_output": "产出放哪（相对 cwd）；kind=run 可不写",
    "mcp.assign.review": "质检过了以后谁验收：leader（你，用 review 工具）/ user（等用户定）/ none（质检过就算完成）",
    "mcp.assign.max_rounds": "最多打回几轮，默认 2",
    "mcp.assign.gates": "机械质检，全过才轮到验收，不过自动打回："
                        "{\"check\":\"exists\",\"path\":\"a.md\"}（文件在且非空，可用通配符）/ "
                        "{\"check\":\"size\",\"path\":\"a.md\",\"min_chars\":200} / "
                        "{\"check\":\"headings\",\"path\":\"a.md\",\"must\":[\"标题\"]} / "
                        "{\"check\":\"json\",\"path\":\"a.json\",\"keys\":[\"k\"]} / "
                        "{\"check\":\"commits\",\"min\":1}（只能用在 git 仓库里，要求工作树干净）/ "
                        "{\"check\":\"command\",\"name\":\"unittest\"}（用户在设置里登记过的命令）",
    "mcp.assign.files": "这张卡打算改的文件或目录（相对 cwd）；几只猫并行时盒子靠它提醒撞车",
    "mcp.review": "验收一张卡：accept 通过并完成；return 打回并自动重派下一轮（note 写进 returned_reason）。"
                  "只有派这张卡的工位能调。可选 feedback：给这只猫以后每张卡都要守的一条约束（≤120 字，"
                  "写哪里偏了 + 下次怎么做）；用户在设置里打开了才会记。",
    "mcp.resolve": "处置没开工 / 失败 / 中断 / 卡住 / 打回待定的卡：redispatch 原卡原工位再派一次（重新走开工检查和送达回执），"
                   "cancel 撤掉这张卡（进 cancelled，不再出现在待办）。只有派这张卡的工位能调。"
                   "redispatch 可以再带 station，改派给另一只猫，卡号不变。",
    "mcp.resolve.station": "改派给哪只猫（不填就还是原来那只）。卡号不变",
    "mcp.report": "打工猫上报：heartbeat / done / blocked / issue，附一句 summary。同一轮同状态只记一次。",
    "mcp.post": "给另一个工位的本机收件箱留一句话。",
    "mcp.read_inbox": "读自己收件箱里的未读留言并标已读。",
    "mcp.wait_for_update": "挂着等猫猫交回卡：等交回待验收 / 失败 / 打回 / 卡住 / 留言，一有动静就立刻返回。"
                           "timeout_s 是最多等多少秒（默认 45，最多 100，最少 1）。"
                           "上限 100 是按 Cursor 的请求时限留的余量：Cursor 大约 115 秒就自己报超时，"
                           "等满了就拿不到 code=none。超过 100 的按 100 等，回话里的 note 说一句，不当成出错。"
                           "等到了返回 code=update 和 events（每条一行）；到点还没动静返回 code=none。"
                           "这些事件要等回话真的送出去才算读过，没送到的下次还会再给。",
    "mcp.instructions": "先调 get_briefing。工位：{sid}（{role}）。",
    "mcp.no_station": "连接设置里没写工位（URL 要带 ?station=工位名）。到「工位」页点首领工牌上的「叫醒首领」重新复制那段话。",
    "mcp.core_unreachable": "boxbox 核心不可达：{err}（先打开猫猫盒子 agentboxbox）",
    "mcp.bad_args_type": "{tool} 的参数得是一组字段，不能是别的样子。",
    "mcp.no_fields": "（无）",
    "mcp.unknown_fields": "不认识这些字段：{unknown}。{tool} 能收的字段：{fields}。",
    "mcp.note_named": "说明字段叫 note。",
    "mcp.return_needs_note": "打回必须写说明，说明字段叫 note，空着的打回不收。",
    "mcp.assign.station.one": "{sid}（模型 {model}）",
    "mcp.assign.station.models": "。可选：{cats}",
}

EN = {
    "mcp.get_briefing": "First call in a new session: your role, the rules, the available tools and a summary of the board.",
    "mcp.get_board": "One line per station: the status word, the card it works on, the minutes. Read only.",
    "mcp.get_todo": "The leader to-do: waiting for review, stuck, sent back, failed, and the idle stations. "
                    "Sorted by who is waiting.",
    "mcp.get_task": "Everything about one task card: the card, the state, the round, the runs, the usage, the report. "
                    "A member only sees its own cards.",
    "mcp.assign": "The leader hands a self-contained task card to a station (a worker cat). Every field of the card is "
                  "described under card; a card without goal / inputs / expected_output / acceptance.review is refused and "
                  "you are told what is missing. Returns a delivery receipt; it does not retry.",
    "mcp.assign.station": "Which station takes it (the worker cat name, see it in get_board)",
    "mcp.assign.title": "A one-line title, shown on the board",
    "mcp.assign.goal": "What to do and how far to go. The card has to stand on its own: the worker cat starts a new "
                        "session and cannot see your conversation with the user",
    "mcp.assign.cwd": "The directory the worker cat works in (absolute path). Put the absolute path of the user's project "
                      "there to touch its files (usually your current working directory); without it the worker cat works in "
                      "its own empty directory and cannot see the user's files. A directory you name here has to exist, "
                      "otherwise the card is refused right away",
    "mcp.assign.inputs": "The files to read (relative to cwd). For an empty directory, or when there is nothing to read, "
                         "write [\"(none, create it)\"]",
    "mcp.assign.expected_output": "Where the output goes (relative to cwd); may be left out when kind=run",
    "mcp.assign.review": "Who reviews it once the checks pass: leader (you, with the review tool) / user (waiting for the "
                         "user) / none (done once the checks pass)",
    "mcp.assign.max_rounds": "How many times it may be sent back, 2 by default",
    "mcp.assign.gates": "Mechanical checks, all of them have to pass before the review, otherwise it is sent back "
                        "automatically: {\"check\":\"exists\",\"path\":\"a.md\"} (the file exists and is not empty, wildcards "
                        "allowed) / {\"check\":\"size\",\"path\":\"a.md\",\"min_chars\":200} / "
                        "{\"check\":\"headings\",\"path\":\"a.md\",\"must\":[\"title\"]} / "
                        "{\"check\":\"json\",\"path\":\"a.json\",\"keys\":[\"k\"]} / "
                        "{\"check\":\"commits\",\"min\":1} (only in a git repository, the working tree has to be clean) / "
                        "{\"check\":\"command\",\"name\":\"unittest\"} (a command the user registered in Settings)",
    "mcp.assign.files": "The files or folders this card is going to change (relative to cwd); the box uses it to warn "
                        "about cats working on the same files",
    "mcp.review": "Review one card: accept passes it and finishes it; return sends it back and dispatches the next round "
                  "automatically (the note goes into returned_reason). Only the station that dispatched the card may call "
                  "it. Optional feedback: one rule this cat has to keep for every later card (≤120 characters: what went "
                  "wrong and what to do next); it is only kept when the user turned it on in Settings.",
    "mcp.resolve": "Deal with the cards that never started / failed / were interrupted / are stuck / were sent back "
                   "and are waiting: redispatch sends the "
                   "same card to the same station again (the start checks and the delivery receipt run again), cancel drops "
                   "the card (it becomes cancelled and leaves the to-do). Only the station that dispatched the card may "
                   "call it. redispatch may also include station, to give the same card to another cat; "
                   "the card number stays the same.",
    "mcp.resolve.station": "Which cat to move the card to (leave it out to keep the same one). The card number stays the same",
    "mcp.report": "The worker cat reports: heartbeat / done / blocked / issue, with a one-line summary. The same status in "
                  "the same round is only recorded once.",
    "mcp.post": "Leave a note in another station's local inbox.",
    "mcp.read_inbox": "Read the unread notes in your own inbox and mark them read.",
    "mcp.wait_for_update": "Wait for the cats to hand a card back: it returns as soon as a card comes back for review / "
                           "fails / is sent back / is stuck / a note arrives. timeout_s is how long to wait at most "
                           "(45 by default, 100 at most, 1 at least). The cap of 100 leaves room for Cursor: "
                           "Cursor times the request out at about 115 seconds, so a full wait would come back as a "
                           "timeout instead of code=none. A number over 100 is waited as 100, and the reply's note says so; "
                           "that is not an error. When something comes back it returns code=update and events "
                           "(one per line); when nothing happens it returns code=none. "
                           "Those events count as read only after the reply is actually sent; "
                           "a reply that never goes out is given again next time.",
    "mcp.instructions": "Call get_briefing first. Station: {sid} ({role}).",
    "mcp.no_station": "The connection has no station (the URL needs ?station=name). On the Stations page, click "
                       "“Wake the leader” on the leader's badge and copy the text again.",
    "mcp.core_unreachable": "agentboxbox isn't running ({err}); open it first",
    "mcp.bad_args_type": "{tool} arguments have to be a set of fields.",
    "mcp.no_fields": "(none)",
    "mcp.unknown_fields": "Unknown fields: {unknown}. Fields {tool} accepts: {fields}.",
    "mcp.note_named": " The explanation field is called note.",
    "mcp.return_needs_note": "A return needs a note. The explanation field is called note, and an empty one is refused.",
    "mcp.assign.station.one": "{sid} (model {model})",
    "mcp.assign.station.models": ". Choices: {cats}",
}
