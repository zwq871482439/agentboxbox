# 安全问题报告 / Security policy

## 怎么报告

发现安全漏洞（比如本机接口能被别的网页或别的用户调用、API key 会被显示或写进日志、MCP 条目能被改成执行别的程序），**请不要开公开 issue**。在 GitHub 仓库的 **Security → Report a vulnerability** 里私下报告，写清楚：

- 用的版本（设置页或托盘提示里能看到，比如 0.3.0）和运行方式（exe / 源码）；
- 怎么复现；
- 你认为会造成什么影响。

我们会在 7 天内回复，修好后在更新说明里致谢（你不想署名就不写）。

## 支持的版本

只修最新发布的版本。

## 设计上的边界

- 核心只监听 `127.0.0.1`。本机上能运行程序的人，本来就能读你的 `data/` 目录，所以「本机另一个程序调用本机接口」不算漏洞，除非它能绕过浏览器的同源限制从网页里发起。
- `data/secrets.json` 是明文保存的（见 [PRIVACY.md](PRIVACY.md)）。这是已知设计，不是漏洞。

---

Please **do not open a public issue** for security problems. Use **Security → Report a vulnerability** on the GitHub repository to report privately, with the version, steps to reproduce and the impact. We reply within 7 days. Only the latest release is supported. The core listens on `127.0.0.1` only, and `data/secrets.json` stores API keys in plain text by design.
