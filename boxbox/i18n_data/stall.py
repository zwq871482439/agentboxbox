# -*- coding: utf-8 -*-
"""卡住提醒、撤卡停不掉、单条命令超时的那几句话。"""
from __future__ import annotations

ZH = {
    "stall.quiet": "命令 {dur}没输出",
    "stall.model": "模型 {dur}没回",
    "stall.notool": "连续 {dur}没有调用工具",
    "stall.recent": "最近一次：{tool}，{at} 开始，{cmd}；最后一行：{line}",
    "stall.kids": "底下还在跑：{kids}",
    "stall.kid": "{name}（{cmd}，已跑 {age}）",
    "stall.kid_sep": "；",
    "stall.no_kids": "底下没有别的进程",
    "stall.report": "{head}。{recent}。{kids}",
    "stall.hard": "命令 {cmd} 跑了 {dur}没结束",
    "stall.cmd_unknown": "这条命令",
    "stall.dur_min": "{n} 分钟",
    "stall.dur_sec": "{n} 秒",
    "ack.cancel_alive": "已撤掉，但这只猫的进程没停掉（进程号 {pid}）",
}

EN = {
    "stall.quiet": "No new output for {dur}",
    "stall.model": "No model reply for {dur}",
    "stall.notool": "No tool call for {dur}",
    "stall.recent": "Last activity: {tool}, started {at}, {cmd}; last line: {line}",
    "stall.kids": "Still running under it: {kids}",
    "stall.kid": "{name} ({cmd}, running {age})",
    "stall.kid_sep": "; ",
    "stall.no_kids": "Nothing else is running under it",
    "stall.report": "{head}. {recent}. {kids}",
    "stall.hard": "Command {cmd} ran for {dur} and did not finish",
    "stall.cmd_unknown": "this command",
    "stall.dur_min": "{n} min",
    "stall.dur_sec": "{n} s",
    "ack.cancel_alive": "Cancelled, but this cat's process is still running (process {pid})",
}
