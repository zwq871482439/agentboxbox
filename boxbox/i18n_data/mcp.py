# -*- coding: utf-8 -*-
"""客户端工具通道里给模型看的话：工具说明、参数说明、连接提示。"""
from __future__ import annotations

ZH = {
    "mcp.get_briefing": "新会话第一条：返回你的角色、规则、可用工具和当前任务概况。",
    "mcp.get_board": "每个帮手一行：状态词、在做哪个任务、分钟。只读。",
    "mcp.get_todo": "编程助手的待办：待确认、卡住、退回待定、失败、闲着的帮手。按谁在等排序。",
    "mcp.get_task": "看一个任务的全部：任务、状态、轮次、运行、用量、回报。member 只能看自己的任务。",
    "mcp.assign": "编程助手派一个自包含的任务给某个帮手。任务里各字段见 card 的说明；"
                  "缺 goal / inputs / expected_output / acceptance.review 会直接拒收并告诉你缺什么。返回送达回执；不重试。",
    "mcp.assign.station": "派给哪个帮手（帮手的名字，get_board 里看）",
    "mcp.assign.title": "一句话标题，任务页上显示",
    "mcp.assign.goal": "要什么、做到什么程度。任务要自包含：帮手是新会话，看不到你和用户的对话",
    "mcp.assign.cwd": "帮手在哪个目录干活（绝对路径）。要读写用户项目里的文件，就写那个项目的绝对路径"
                      "（通常就是你当前的工作目录）；不写的话帮手在它自己的空目录里干，看不到用户的文件。"
                      "写了的目录必须已经存在，不然这个任务直接被拒收",
    "mcp.assign.inputs": "要读的文件（相对 cwd）。空目录、没有现成文件可读时写 [\"（无，新建）\"]",
    "mcp.assign.expected_output": "产出放哪（相对 cwd）；kind=run 可不写",
    "mcp.assign.review": "自动检查过了以后谁确认：leader（你，用 review 工具）/ user（等用户定）/ none（自动检查过就算完成）",
    "mcp.assign.max_rounds": "最多退回重做几轮，默认 2",
    "mcp.assign.gates": "自动检查，全过才轮到确认，不过自动退回重做："
                        "{\"check\":\"exists\",\"path\":\"a.md\"}（文件在且非空，可用通配符）/ "
                        "{\"check\":\"size\",\"path\":\"a.md\",\"min_chars\":200} / "
                        "{\"check\":\"headings\",\"path\":\"a.md\",\"must\":[\"标题\"]} / "
                        "{\"check\":\"json\",\"path\":\"a.json\",\"keys\":[\"k\"]} / "
                        "{\"check\":\"commits\",\"min\":1}（只能用在 git 仓库里，要求工作树干净）/ "
                        "{\"check\":\"command\",\"name\":\"unittest\"}（用户在设置里登记过的命令）",
    "mcp.assign.files": "这个任务打算改的文件或目录（相对 cwd）；几个帮手并行时盒子靠它提醒撞车",
    "mcp.review": "确认一个任务：accept 通过并完成；return 退回重做并自动重派下一轮（note 写进 returned_reason）。"
                  "只有派这个任务的编程助手能调。可选 feedback：给这个帮手以后每个任务都要守的一条约束（≤120 字，"
                  "写哪里偏了 + 下次怎么做）；用户在设置里打开了才会记。",
    "mcp.resolve": "处置没开工 / 失败 / 中断 / 卡住 / 退回待定的任务：redispatch 原任务原帮手再派一次（重新走开工检查和送达回执），"
                   "cancel 撤掉这个任务（进 cancelled，不再出现在待办）；正在做的任务也能 cancel，"
                   "盒子会停掉帮手和它起的所有程序。只有派这个任务的编程助手能调。"
                   "redispatch 可以再带 station，改派给另一个帮手，任务号不变。",
    "mcp.resolve.station": "改派给哪个帮手（不填就还是原来那个）。任务号不变",
    "mcp.report": "帮手上报：heartbeat / done / blocked / issue，附一句 summary。同一轮同状态只记一次。",
    "mcp.post": "给另一个帮手的本机收件箱留一句话。",
    "mcp.read_inbox": "读自己收件箱里的未读留言并标已读。",
    "mcp.wait_for_update": "挂着等帮手做完任务：等做完了待确认 / 失败 / 退回重做 / 卡住 / 留言，一有动静就立刻返回。"
                           "timeout_s 是最多等多少秒（默认 45，最多 100，最少 1）。"
                           "上限 100 是按 Cursor 的请求时限留的余地：Cursor 大约 115 秒就自己报超时，"
                           "等满了就拿不到 code=none。超过 100 的按 100 等，回话里的 note 说一句，不当成出错。"
                           "等到了返回 code=update 和 events（每条一行）；到点还没动静返回 code=none。"
                           "这些事件要等回话真的送出去才算读过，没送到的下次还会再给。",
    "mcp.instructions": "你是编程助手（{sid}）。用户把你连进了猫猫盒子：盒子里的帮手替你干活，"
                       "你只做三件事——写任务、派活、确认。\n"
                       "- 用户说「交给帮手」或让你把活分出去时，写成任务用 assign 派出去，不要自己动手做；"
                       "用户说得含糊，先问一句要什么再派。\n"
                       "- 每轮开始先调 get_todo，按「谁在等」排序处理；回话里出现「还等你处理」先处理这些，再派新任务。\n"
                       "- 任务要自包含：帮手是新会话，看不到你和用户的对话。goal 写清要什么，cwd 写用户项目的绝对路径，"
                       "inputs 列要读的文件，expected_output 和 acceptance 写清产出在哪、怎么算做完。\n"
                       "- 挑帮手看 get_board（各自的模型、状态、额度）；有帮手闲着就把能并行的任务一轮全派出去。\n"
                       "- 派完调 wait_for_update 挂着等做完；做完了的任务用 review 确认（accept 过、return 退回重做），"
                       "没确认不要跟用户说「做完了」。\n"
                       "- 完整规则和当前任务清单：先调 get_briefing。",
    "mcp.instructions.member": "先调 get_briefing。你是帮手 {sid}（{role}）。",
    "mcp.prompt.dispatch": "把用户的一件事交给帮手：拆成自包含的任务派出去，等做完并确认。",
    "mcp.prompt.dispatch.task": "用户要交给帮手的那件事（原话）",
    "mcp.prompt.dispatch.text": "用户要把这件事交给帮手：\n\n{task}\n\n按编程助手的规矩办：\n"
                                "1. 先调 get_todo，有在等的任务先处理。\n"
                                "2. 把这件事按写任务规则拆成自包含的任务（大活拆成几个小任务）：goal 写清要什么、"
                                "cwd 写用户项目的绝对路径、inputs 列要读的文件、expected_output 写产出在哪、"
                                "acceptance 写自动检查和确认人。\n"
                                "3. 用 assign 把任务派给帮手；有帮手闲着就把能并行的任务一轮全派出去。\n"
                                "4. 派完调 wait_for_update 等做完，不要干等用户来问。\n"
                                "5. 做完了的任务用 review 确认：accept 通过，return 带具体说明退回重做；"
                                "没确认不要说「做完了」。",
    "mcp.no_station": "连接设置里没写名字（URL 要带 ?station=名字）。到帮手页点编程助手工牌上的「叫醒」重新复制那段话。",
    "mcp.core_unreachable": "连不上猫猫盒子（agentboxbox）：{err}（先打开猫猫盒子）",
    "mcp.bad_args_type": "{tool} 的参数得是一组字段，不能是别的样子。",
    "mcp.no_fields": "（无）",
    "mcp.unknown_fields": "不认识这些字段：{unknown}。{tool} 能收的字段：{fields}。",
    "mcp.note_named": "说明字段叫 note。",
    "mcp.return_needs_note": "退回重做必须写说明，说明字段叫 note，空着的不收。",
    "mcp.assign.station.one": "{sid}（模型 {model}）",
    "mcp.assign.station.models": "。可选：{cats}",
}

EN = {
    "mcp.get_briefing": "First call in a new session: your role, the rules, the available tools and a summary of the current tasks.",
    "mcp.get_board": "One line per helper: the status word, the task it works on, the minutes. Read only.",
    "mcp.get_todo": "Your coding assistant's to-do: waiting for confirmation, stuck, sent back, failed, and the idle helpers. "
                    "Sorted by who is waiting.",
    "mcp.get_task": "Everything about one task: the task, the state, the round, the runs, the usage, the report. "
                    "A helper only sees its own tasks.",
    "mcp.assign": "Your coding assistant hands a self-contained task to a helper. Every field of the task is "
                  "described under card; a task without goal / inputs / expected_output / acceptance.review is refused and "
                  "you are told what is missing. Returns a delivery receipt; it does not retry.",
    "mcp.assign.station": "Which helper takes it (the helper name, see it in get_board)",
    "mcp.assign.title": "A one-line title, shown on the tasks page",
    "mcp.assign.goal": "What to do and how far to go. The task has to stand on its own: the helper starts a new "
                        "chat and cannot see your conversation with the user",
    "mcp.assign.cwd": "The directory the helper works in (absolute path). Put the absolute path of the user's project "
                      "there to touch its files (usually your current working directory); without it the helper works in "
                      "its own empty directory and cannot see the user's files. A directory you name here has to exist, "
                      "otherwise the task is refused right away",
    "mcp.assign.inputs": "The files to read (relative to cwd). For an empty directory, or when there is nothing to read, "
                         "write [\"(none, create it)\"]",
    "mcp.assign.expected_output": "Where the output goes (relative to cwd); may be left out when kind=run",
    "mcp.assign.review": "Who confirms it once the auto-checks pass: leader (you, with the review tool) / user (waiting for the "
                         "user) / none (done once the auto-checks pass)",
    "mcp.assign.max_rounds": "How many times it may be sent back, 2 by default",
    "mcp.assign.gates": "Auto-checks, all of them have to pass before the confirmation, otherwise it is sent back "
                        "automatically: {\"check\":\"exists\",\"path\":\"a.md\"} (the file exists and is not empty, wildcards "
                        "allowed) / "
                        "{\"check\":\"size\",\"path\":\"a.md\",\"min_chars\":200} / "
                        "{\"check\":\"headings\",\"path\":\"a.md\",\"must\":[\"title\"]} / "
                        "{\"check\":\"json\",\"path\":\"a.json\",\"keys\":[\"k\"]} / "
                        "{\"check\":\"commits\",\"min\":1} (only in a git repository, the working tree has to be clean) / "
                        "{\"check\":\"command\",\"name\":\"unittest\"} (a command the user registered in Settings)",
    "mcp.assign.files": "The files or folders this task is going to change (relative to cwd); the box uses it to warn "
                        "about helpers working on the same files",
    "mcp.review": "Confirm one task: accept passes it and finishes it; return sends it back and hands off the next round "
                  "automatically (the note goes into returned_reason). Only the coding assistant that handed off the task may "
                  "call it. Optional feedback: one rule this helper has to keep for every later task (≤120 characters: what "
                  "went wrong and what to do next); it is only kept when the user turned it on in Settings.",
    "mcp.resolve": "Deal with the tasks that never started / failed / were interrupted / are stuck / were sent back "
                   "and are waiting: redispatch sends the "
                   "same task to the same helper again (the start checks and the delivery receipt run again), cancel drops "
                   "the task (it becomes cancelled and leaves the to-do); cancel also works on a task that is running, and "
                   "the box stops the helper and every program it started. Only the coding assistant that handed off the task "
                   "may call it. redispatch may also include station, to give the same task to another helper; "
                   "the task number stays the same.",
    "mcp.resolve.station": "Which helper to move the task to (leave it out to keep the same one). The task number stays the same",
    "mcp.report": "The helper reports: heartbeat / done / blocked / issue, with a one-line summary. The same status in "
                  "the same round is only recorded once.",
    "mcp.post": "Leave a note in another helper's local inbox.",
    "mcp.read_inbox": "Read the unread notes in your own inbox and mark them read.",
    "mcp.wait_for_update": "Wait for the helpers to finish a task: it returns as soon as a task is done and waiting for "
                           "confirmation / fails / is sent back / is stuck / a note arrives. timeout_s is how long to wait at "
                           "most (45 by default, 100 at most, 1 at least). The cap of 100 leaves room for Cursor: "
                           "Cursor times the request out at about 115 seconds, so a full wait would come back as a "
                           "timeout instead of code=none. A number over 100 is waited as 100, and the reply's note says so; "
                           "that is not an error. When something comes back it returns code=update and events "
                           "(one per line); when nothing happens it returns code=none. "
                           "Those events count as read only after the reply is actually sent; "
                           "a reply that never goes out is given again next time.",
    "mcp.instructions": "You are the coding assistant ({sid}). The user plugged you into agentboxbox: "
                       "the helpers in the box work for you, and you do exactly three things — write tasks, hand off, confirm.\n"
                       "- When the user says \"hand this to the helpers\" or asks you to split work out, write it as a task "
                       "and hand it off with assign; never do the work yourself. If the request is vague, ask what is wanted "
                       "first.\n"
                       "- Start every turn with get_todo and handle whoever is waiting first; when a reply says \"waiting for "
                       "you\", clear those tasks before handing off new ones.\n"
                       "- Tasks must stand on their own: a helper starts a fresh chat and cannot see your conversation with "
                       "the user. goal says what is wanted, cwd is the absolute path of the user's project, inputs lists the "
                       "files to read, expected_output and acceptance say where the result goes and what counts as done.\n"
                       "- Pick helpers with get_board (their model, status, allowance); when helpers are idle, hand off every "
                       "task that can run in parallel in one turn.\n"
                       "- After handing off, wait with wait_for_update; confirm every task that comes back done with review (accept "
                       "to pass, return to send it back). Never tell the user \"done\" without a confirmation.\n"
                       "- For the full rules and the current task list, call get_briefing first.",
    "mcp.instructions.member": "Call get_briefing first. You are helper {sid} ({role}).",
    "mcp.prompt.dispatch": "Hand one of the user's tasks to the helpers: split it into self-contained tasks, hand off, "
                            "wait and confirm.",
    "mcp.prompt.dispatch.task": "The task the user wants handed to the helpers (their words)",
    "mcp.prompt.dispatch.text": "The user wants this handed to the helpers:\n\n{task}\n\nPlay it by the coding assistant's "
                                "rules:\n"
                                "1. Call get_todo first and clear whatever is waiting.\n"
                                "2. Split the task into self-contained tasks by the task-writing rules (big jobs become "
                                "several small tasks): goal says what is wanted, cwd is the absolute path of the user's "
                                "project, inputs lists the files to read, expected_output says where the result goes, "
                                "acceptance says the auto-checks and who confirms.\n"
                                "3. Hand each task off with assign; when helpers are idle, hand off every task that can run "
                                "in parallel in one turn.\n"
                                "4. Wait with wait_for_update after handing off; do not sit idle waiting for the user to ask.\n"
                                "5. Confirm every task that comes back done with review: accept to pass, return with a concrete note to "
                                "send it back. Never say \"done\" without a confirmation.",
    "mcp.no_station": "The connection has no name (the URL needs ?station=name). On the Helpers page, click "
                       "“Wake” on your coding assistant's badge and copy the text again.",
    "mcp.core_unreachable": "agentboxbox isn't running ({err}); open it first",
    "mcp.bad_args_type": "{tool} arguments have to be a set of fields.",
    "mcp.no_fields": "(none)",
    "mcp.unknown_fields": "Unknown fields: {unknown}. Fields {tool} accepts: {fields}.",
    "mcp.note_named": " The explanation field is called note.",
    "mcp.return_needs_note": "A return needs a note. The explanation field is called note, and an empty one is refused.",
    "mcp.assign.station.one": "{sid} (model {model})",
    "mcp.assign.station.models": ". Choices: {cats}",
}
