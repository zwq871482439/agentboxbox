"""能力清单的名字、说明和代价。"""

ZH = {
    "cap.ponytail.name": "写代码规则",
    "cap.ponytail.desc": "让帮手按少写、写全的规则改代码，full 比 lite 管得更细。",
    "cap.ponytail.cost": "off 不多花用量；lite / full 会多读一份规则，多花一点用量；不占磁盘，不联网。",
    "cap.search_tools.name": "代码搜索工具",
    "cap.search_tools.desc": "给帮手 rg / fd，按内容或文件名更快找到代码。",
    "cap.search_tools.cost": "工具已随盒子装好；几乎不多花用量，不额外占磁盘，不联网。",
    "cap.repo_map.name": "仓库地图",
    "cap.repo_map.desc": "派活时给帮手一页仓库结构和重要符号，少花时间找代码。",
    "cap.repo_map.cost": "每次派活会多花一些用量；只占少量临时磁盘，不联网。",
    "cap.member_feedback.name": "任务确认意见",
    "cap.member_feedback.desc": "把你的编程助手确认任务时留下的约束带给帮手，下次少犯同样的问题。",
    "cap.member_feedback.cost": "会多读一点历史意见，多花一点用量；意见只占少量磁盘，不联网。",
    "cap.git_no_editor.name": "Git 不弹编辑器",
    "cap.git_no_editor.desc": "帮手运行 Git 时自动关掉编辑器、分页和交互提问，避免任务停住。",
    "cap.git_no_editor.cost": "本身不多花用量，不占磁盘，不联网。",
    "cap.command_guard.name": "命令卡死兜底",
    "cap.command_guard.desc": "命令太久没有输出会提醒；跑到上限或撤掉任务时，把它和它带起来的程序一起停掉。",
    "cap.command_guard.cost": "本身不多花用量，不占磁盘，不联网。",
}

EN = {
    "cap.ponytail.name": "Coding rules",
    "cap.ponytail.desc": "Gives helpers rules for small, complete code changes; full is more detailed than lite.",
    "cap.ponytail.cost": "off adds no usage; lite and full add a little usage to read the rules; no disk space or network access.",
    "cap.search_tools.name": "Code search tools",
    "cap.search_tools.desc": "Lets helpers use rg and fd to find code faster by content or file name.",
    "cap.search_tools.cost": "The tools are already bundled; almost no extra usage or disk space, and no network access.",
    "cap.repo_map.name": "Repository map",
    "cap.repo_map.desc": "Gives helpers a page of repository structure and important symbols when work is assigned, so they find code faster.",
    "cap.repo_map.cost": "Each assignment uses a little more; only a small amount of temporary disk space, and no network access.",
    "cap.member_feedback.name": "Task confirmation feedback",
    "cap.member_feedback.desc": "Carries constraints left by your coding assistant when confirming tasks to helpers, reducing repeated mistakes.",
    "cap.member_feedback.cost": "Reading past feedback adds a little usage; feedback takes little disk space, and no network access is needed.",
    "cap.git_no_editor.name": "No Git editor pop-ups",
    "cap.git_no_editor.desc": "Disables editors, pagers, and interactive questions in helpers' Git commands so tasks do not stall.",
    "cap.git_no_editor.cost": "Adds no usage or disk space by itself, and needs no network access.",
    "cap.command_guard.name": "Stuck command protection",
    "cap.command_guard.desc": "Warns when a command has no output for too long; at the limit or when a task is cancelled, it stops "
                              "the command and everything it started.",
    "cap.command_guard.cost": "Adds no usage or disk space by itself, and needs no network access.",
}
