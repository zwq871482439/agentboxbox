# Data use and privacy

Applies to every version of agentboxbox from 0.4 on (double-click the exe, or run it from the source). This statement is updated with every release; the change history is the history of this file in the repository.

## In one sentence

agentboxbox runs only on your own computer and **collects and uploads nothing**: no account, no server, no usage statistics, no telemetry, no crash reports. The only thing that leaves your computer is what you send to **the model provider you chose** when a worker cat does a job; that part is covered by that provider's privacy policy and terms of service.

## What is stored on your computer

Everything is in the data folder `data/`: next to the exe when you double-click it, in the repository's `data/` folder when you run it from the source, and in whatever folder the `BOXBOX_DATA` environment variable points to.

- `stations.json`: the station settings (name, which client and model, working folder).
- `secrets.json`: the API keys you type in on the page. They are **stored in plain text**, only on this computer, so the worker cat can reach the provider you picked; the page and the interface never show them. The box does not read the environment variables of your system as keys: only the copy stored in this file counts.
- `boxbox.db`: job cards, state changes, activity, usage.
- `tasks/`, `sessions/`: the instructions and the handover report of every card, plus the session records of the worker cats (Pi). A session record holds the task content and the pieces of files the cat read while working.
- `logs/`: run logs.
- `pi/`: the configuration of Pi. It only holds the name of the variable the box uses internally (Pi looks the key up by that name), never the key itself.
- `tmp/`: temporary files, the intermediate files of a running job, one subfolder per card; you can delete the whole folder when no card is running, and the settings page can clean it up for you.

Delete the `data/` folder, or click “reset everything” on the settings page, and all of it is gone. Uninstalling means deleting the exe and the `data/` folder.

## When it goes online, and to whom

agentboxbox itself only listens on `127.0.0.1`; it does not open a port to the local network or to the internet. It only connects out in the cases below, and each of them needs you to set it up or click it first:

1. **A worker cat does a job**: Pi sends the job card, the prompt, the content of the files it read to do the job and your API key to **the model provider you picked for that station** (Kimi, Zhipu, MiniMax, or the address you typed in yourself). Only hand a project to a provider you are willing to give it to. When you hire a worker cat and click “test the connection”, the same key is used to send that provider one short line (“reply with two letters: ok”), to see whether the key is right and whether there is credit left.
2. **Checking the remaining quota**: after you turn on the quota check for a station, that station's API key is used to call the usage endpoint of the same provider (the addresses of Kimi, Zhipu and MiniMax are built in, and you can type in your own).
3. **Updating the provider list**: after you click “update” and confirm on the settings page, the public model list is downloaded from models.dev. This step sends none of your data.

A few more things worth knowing:

- Your AI client (Cursor, Claude Code, Codex and the like) talks to the local agentboxbox over MCP. How the client talks to its own provider does not go through agentboxbox and is covered by the client's own terms.
- When agentboxbox starts Pi it switches off Pi's own install statistics, version check and startup network calls (`PI_TELEMETRY=0`, `PI_SKIP_VERSION_CHECK=1`, `PI_OFFLINE=1`); it also does not read the skills and prompt templates of the AI software on your computer (Pi is started with `--no-skills --no-prompt-templates`).
- The embedded window uses the Microsoft Edge WebView2 that comes with Windows; its diagnostic data follows your Windows privacy settings.

## What it changes on your computer

- When you register a leader or a worker cat, agentboxbox gives you a short text that explains how that station connects. Whether you add this connection to the AI app you use is your own decision: you can add it yourself, or you can let the AI inside that app add it for you. agentboxbox does not edit the configuration files of your AI software, and it neither backs them up nor overwrites them.
- When you tick “start with Windows”, a shortcut is placed in the Windows “Startup” folder; unticking it deletes the shortcut.
- A worker cat can read and write files in its working folder and run commands there; that is how it does the job. Give it a folder of its own or a copy of the project.

## Diagnostics

“Copy the diagnostics” on the self-check page only copies to your clipboard; nothing is sent automatically. Before copying, the user name in the paths is replaced with `~` and anything that looks like a key is replaced with `***`. Look at it yourself before you paste it into a GitHub issue.

## Contact

Questions and ideas: open an issue in the GitHub repository. Security problems: report them privately as described in [SECURITY.md](SECURITY.md), not in a public issue.
