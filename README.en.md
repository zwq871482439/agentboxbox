# agentboxbox (猫猫盒子)

[中文版](README.md)

**Give your AI coding assistant a few helpers.** Your coding assistant breaks the work up into tasks and checks the results; agentboxbox hands that work to other models you set up, runs them at the same time, and sends the results back to your chat.

It's for someone who already uses a coding assistant (Cursor, Claude Code or Codex). Everything runs on your own machine with no account and no server; nothing leaves it except the requests a helper sends to the model provider you picked for it (see [PRIVACY.en.md](PRIVACY.en.md)). agentboxbox never changes the settings of your AI software.

Current state: 0.6.0 is the current release. The exe is Windows-only; the pages, the texts for your coding assistant and the helpers, and the office all speak Chinese and English. The language follows your system on first launch and you can switch it in the welcome window or in Settings.

## What it does

- Your coding assistant keeps talking with you and breaking the work up; whatever it hands out, it writes as a **self-contained task** (what to make, which files to read, what to hand in, when it counts as done) and gives it to a helper;
- When a helper hands a task back, **auto checks** run first (mechanical checks, no usage spent), then your coding assistant **confirms** it or **sends it back to redo**;
- Every hand-back comes with a **hand-off sheet**: which files changed, which checks ran, what is unfinished or uncertain, what you need to confirm;
- All the waiting is the box's job (delivery receipts, heartbeats, a watchdog); no model polls on its own;
- The home page is a pixel office: who is working, who is idle, who is resting, and one line per helper saying what it is doing.

A helper works in one of two ways (one per helper):

| Way of working | How it works | Good for |
|---|---|---|
| Run it with an API key | The box starts one Pi process per task (pick a model platform and a model, enter the API key); it exits when done | Anyone with a model platform API key, pay-as-you-go or a coding plan |
| Check-in mode | Your AI app opens a new chat every few minutes to pick up a task: the box writes the task to a file, the app reads it and writes a report back; no API key needed, any app works | People who already work inside an AI app |

Your coding assistant is the Cursor, Claude Code or Codex you already use (or any other AI app that speaks MCP). Install agentboxbox into it once and it can call the box's tools: hand out work, wait for results, confirm. The box doesn't host a coding assistant of its own and has no place to "talk to it inside the box"; it always lives in your app. You can have more than one: when two projects each have their own chat, use "Add another coding assistant" from the "…" at the top right of the Helpers page. Each coding assistant only sees and confirms the tasks it handed out; the helpers are shared.

## Installing

- **Requirements**: Windows 10 / 11, 64-bit. The exe needs no Python or Node: both are packed inside, and so are the search tools. Helpers run commands in Git Bash (it comes with Git); if Git is missing, the self-check says so.
- **With the exe**: download `agentboxbox_<version>.exe` from https://github.com/zwq871482439/agentboxbox/releases (every release carries its checksum and its notes). Make a fresh folder for it, put the exe there and double-click. Two folders appear next to the exe: `data\` holds configuration and records (helpers, keys, tasks, logs) — **don't delete it casually**; `tmp\` holds throw-away scratch from work in progress, cleared automatically when a task is done or cancelled — **safe to delete any time no task is running** (the "Space used" row in Settings cleans it too). In `data\`, the run records of finished tasks are compressed after a few days and deleted later; the number of days is under Advanced in Settings. Don't drop the exe into a crowded desktop or your downloads folder.
- **First launch**: onboarding windows pop up over the office on the home page, and a cat icon appears in the tray. The × at the top right only hides the window to the tray; to quit, right-click the tray cat and choose "Exit". To start with Windows, tick "Start with Windows" in the tray menu.
- **Uninstalling**: exit from the tray and delete the whole folder. If you turned on "Start with Windows", untick it first (otherwise a shortcut stays in the Windows Startup folder). The connection you installed into your coding assistant lives in that app's own MCP settings; remove it there if you want. Windows keeps one registry entry for how the tray icon is shown; it does nothing.
- **From source (for developers)**: needs Python 3.11+. Run `python -m boxbox serve` in the repository root and open `http://127.0.0.1:8878`.

### Upgrading

- **Simplest**: exit the old version from the tray, put the new exe in the same folder and double-click it. `data\` carries over; helpers, settings and tasks are all still there. Delete the old exe when you're done.
- **Into a new folder**: exit the old version from the tray, open the new one, and use Settings → Data and privacy → "Import old version" with the old folder (or the `data\` inside it). Don't copy `data\` while the old version is still running: anything handed out, handed back or confirmed there afterwards would not come along.
- **Coming from 0.5 with a coding assistant that connected by pasting a text**: it keeps working. To stop pasting into new chats, open "…" → "How to give work" on the coding assistant's badge on the Helpers page and click "Install into Cursor", or copy the Claude Code / Codex command into a terminal and run it once.

## Onboarding

On first launch, pixel windows pop up over the office one after another and take a few minutes (close or refresh any time; the box remembers where you were):

1. **Welcome**: one sentence on what this is, and a flow strip (your coding assistant → dispatch → the helpers → results back → your chat).
2. **Install into your coding assistant**: pick the tab for the one you use. For Cursor, click "Install into Cursor" and click Enable when Cursor asks; Claude Code and Codex each get one command to run in a terminal; other apps get a connection snippet. Once installed it connects on its own and this step turns green — **no need to type anything in its chat**. You click every button and run every command yourself; **agentboxbox never changes the settings of any software on your computer**. You also pick a look for it here.
3. **Add a helper**: give it a name and a look, then pick how it works. "Run it with an API key" asks for a model platform, a model and a key, and "Test connection" really asks the platform once; check-in mode needs no key. A failed test doesn't block you: the helper is added anyway, its tasks wait in the queue and start once the connection works.
4. **Hand out the first task**: back in your coding assistant, say "hand XX to the helpers" in any chat; Cursor also gets a "Dispatch in Cursor" button.

All texts in the pages, onboarding and the office follow the interface language. It is set from your system language on first launch; the welcome window has a small "中文 / English" switch, and you can change it later in Settings.

## Everyday use

Four pages in the top bar: **Tasks, Helpers, Capabilities, Settings**; on the right, "Working / Success rate / Check".

**Home (`/`) is the office**:

- Right after onboarding, a small "Start in three steps" card sits at the top left and folds away once all three are done; at the bottom right is the legend: ! waiting for you, ? waiting for your coding assistant, × did not work out, Zzz resting.
- On the left of the scene are the "Activity" and "Usage" buttons (small panels, with a red dot when something new happened) and a day/night switch (auto / dawn / day / dusk / night; auto follows the computer's clock, with times set in Settings).
- Next to the meeting-room projector stands a party arcade: watch a movie, play a round, or send the cats back to work. The cats also organize themselves: naps, late-night snacks, stand-ups, a celebration after a batch.
- **Click a cat for details**: state, current task, how many are queued, quota left, recent activity; for a cat that is working you also see its latest actions (what it read, changed, ran), refreshed every 3 seconds — view only.

**Tasks (`/board`)**: three blocks by default — helpers (one status line each), what waits for you, and the task list. Click a task for its timeline and hand-off sheet; the raw task and run records are under Advanced. Usage and efficiency are folded into "What it cost", closed by default and computed only when opened; efficiency can show each task's wait-to-start / working / wait-to-confirm time per coding assistant and per batch.

**Helpers (`/stations`)**: lanyard badges — the coding assistant plus helpers A–F, 7 seats. Click a badge to change its settings (model platform, model, key and "Test connection"; the rest is under Advanced). The "…" on a badge holds rename, change look, copy, details and delete; the coding assistant's "…" also has "How to give work" (install the box into it, or copy a wake-up text). Renaming changes only the display name; tasks, quota, key and connection stay the same.

**Capabilities (`/capabilities`)**: the switches for how helpers work, each with what it does, what it costs, results from the last 30 days, source and license: coding rules (on by default), code search tools, repo map and task confirmation notes (these three off by default).

**Settings (`/settings`)**: a few common items (language, desktop notifications, office day/night); Advanced holds reminder timing, stuck alerts and how run records are kept; "Space used" with a clean button; the privacy notice and licenses open in full on click; "Reset everything" at the bottom (two confirmations, then onboarding from scratch).

**Helper states**:

| State | Meaning |
|---|---|
| Working | Doing a task ("Working · N tasks queued" when more are waiting); the status line says what it is reading, changing or running |
| Idle | Nothing to do; ready for work |
| Resting | Can't work right now: out of quota / rate limited / cannot connect / server error. Shows the reason and when it is expected back (out of quota means resting until the reset time in the error, together with every helper on the same key); it comes back on its own and continues |
| Config problem | Wrong model id or key; takes no work until you fix it on the Helpers page |
| Disabled | You turned it off in its settings; it doesn't come back on its own |

**What a queued task is waiting for**: each queued task says what it waits for — a helper finishing its current task, a helper coming back from rest, or the connection coming back. A helper does one task at a time; to run more at once on the same model platform, add more helpers (or copy one from the "…" on its badge). A task stopped before it started shows "Never started"; it is not a failure, and your coding assistant can send it again or cancel it.

**Tasks cut off by a model error**: if a helper hits a model error halfway (cannot connect, rate limit, server error), the task is neither failed nor lost: the helper rests, the task goes back to the queue, and the helper continues the same conversation when it is back. A task resumes like this up to three times before it is marked "Interrupted" for you and your coding assistant to decide.

**Stopping a task**: your coding assistant can cancel a task that is running; the box stops the helper and every program it started in that round. When a round ends, anything the helper started that is still running (test windows, background scripts) is stopped too.

**Interrupted tasks** (left unfinished by the last quit or crash) are offered on the next home-page visit: continue the same conversation, leave it to your coding assistant, or leave them for now.

**Desktop notifications**: your coding assistant lives in your own app, and the box can't wake an idle chat there. So when a task comes back, didn't work out, gets stuck or needs a decision, the box shows a Windows notification so you can nudge it in the chat. Turn it off in Settings if you don't want it.

**Quota**: three coding plans are recognised — Kimi Code membership, Zhipu GLM Coding Plan, MiniMax Token Plan (entering their API address picks the right lookup). For anything else choose "Custom" under Advanced in the helper's settings and give the lookup URL and the path of the used percentage in its answer. Results show in the helper's details and in "What it cost" on the Tasks page.

When something looks wrong, start with "Check" in the top bar (each failed item says what to do) or the check page (`/doctor`) and its "Copy the diagnostics" (paths and keys are masked; read it once more before posting an issue). What changed in each version is in [`docs/release-0.6.md`](docs/release-0.6.md).

## For developers

Commands, concepts, endpoints and the repository layout. You don't need this section for everyday use.

### Command reference

Every command takes `--lang zh|en` to pick the language of its output (without it, the command follows the language of the box).

| Command | What it does |
|---|---|
| `python -m boxbox serve [--port 8878]` | Start the core (HTTP + watchdog + SQLite); listens on 127.0.0.1 only |
| `python -m boxbox tray [--show] [--port 8878]` | Tray shell: tray icon (our own ctypes code) + embedded window (needs `pip install pywebview`); double-clicking the exe equals `tray --show` |
| `python -m boxbox mcp --station <helper> --core <URL>` | MCP stdio facade, for clients that don't accept a `url` by hand. Everything the box hands out writes only `http://127.0.0.1:8878/mcp?station=<helper>`, so clients connect straight to the core and spawn nothing |
| `python -m boxbox doctor [--json] [--no-core]` | Self-check: core / data dir / coding assistant / Pi / Git Bash / templates |
| `python -m boxbox board` | Helpers at a glance: one row per helper |
| `python -m boxbox todo` | The coding assistant's to-do: waiting to confirm, stuck, idle helpers |
| `python -m boxbox task <id>` | Everything about one task |
| `python -m boxbox wait [--timeout 600] [--station <coding assistant>] [--port 8878]` | Wait for a task to come back: prints new events (exit 0), nothing came (2), core not running (3) |
| `python -m boxbox report --task <id> --status done --summary "..."` | Helper report (heartbeat / done / blocked / issue) |
| `python -m boxbox assign --station <helper> --card card.json` | Hand out a task (normally your coding assistant calls assign) |
| `python -m boxbox review --task <id> --verdict accept --note "..."` | Confirm: accept, or return (send it back to redo) |

If a core is already listening on the port, `tray` (and double-clicking the exe) attaches to it instead of starting another.

### Concepts

| Concept | Meaning |
|---|---|
| Helper (station / member) | One seat: its name + how it works (run it with an API key / check-in mode). In code and endpoints a seat is a station and a helper's role is member |
| Coding assistant (leader) | The seat of your AI coding assistant: writes tasks, hands them out (assign), confirms (review). There can be several; each handles only the tasks it handed out |
| Task (card) | The only unit of dispatch, **self-contained** (a helper's fresh chat has no old context): `goal` / `inputs` / `expected_output{kind,path}` / `acceptance{review}` are all required; assign rejects the task without them |
| Auto checks (gates) | Mechanical checks run on every hand-back first (exists / headings / command / commits / json / size); no usage spent; any failure sends the task back to redo without bothering your coding assistant. The task field is `acceptance.gates` |
| Confirm (review) | Whoever hands it out confirms it: after the auto checks pass, that coding assistant decides (or leaves it to you, or "auto checks passing is enough") |
| Way of working (runner) | How a helper works: `once` (one Pi process per task) / `scheduled` (check-in mode: reads the exchange file); a coding assistant is `manual` (it lives in your AI app) |
| Language | The interface language lives in the setting `ui_lang` (zh / en) and falls back to the system language when it is not set; the page word lists are in `boxbox/static/i18n-*.js`, the backend ones in `boxbox/i18n_data/` |

### Pages and endpoints

Pages (all under `http://127.0.0.1:8878`):

- `/` home (the office scene): top bar + full-screen office; day/night switch, Activity and Usage buttons and the party arcade live inside the scene; click a cat for details and its live actions; **onboarding happens here, window by window**
- `/board` tasks: helpers (one status line each), what waits for you, tasks; a task's details show its timeline and hand-off sheet; "What it cost" (usage + efficiency) is folded by default
- `/stations` helpers: lanyard badges (coding assistant + A–F); click a badge to change its settings; the "…" holds rename, look, copy, details, delete and how to give work; "Add another coding assistant"
- `/capabilities` capabilities: the switches for how helpers work, with costs, measured results, sources and licenses
- `/settings` settings: a few common items, data & privacy (space used, import from an old version), advanced (reminder timing, stuck alerts, how run records are kept), reset everything
- `/doctor` self-check: per-item results, what to do, copy the diagnostics
- `/office` the office scene on its own (the home page embeds this one)

Endpoints (GET is read-only; writes accept same-origin local requests only; `/mcp?station=<helper>` and `/rpc/<tool>` speak JSON-RPC for models):

- `/api/meta` top-bar data: running count, success rate, alerts
- `/api/stations` per helper: state word, status line, current task, minutes, seat
- `/api/stations/live?id=<helper>` the latest actions of a working helper (reads only the tail of the current run record)
- `/api/stations/label` (POST) change the display name
- `/api/stations/detail` helper detail (config without the key + connection + dispatch log + quota)
- `/api/tasks` the task list (`?state=` filter), each task with its queue reason
- `/api/tasks/<id>` everything about one task: the task, runs, raw report, measured usage, timeline, hand-off sheet
- `/api/todo` to-do: waiting to confirm, stuck, sent back and pending, interrupted, never started, failed, idle helpers
- `/api/interrupted` tasks interrupted by the last quit or crash (POST `/resume` to continue, `/dismiss` to leave them)
- `/api/timeline` recent runs and events
- `/api/tokens` measured usage (only what can be measured exactly; helpers without an API read "not counted")
- `/api/doctor` self-check results (JSON; `?text=1` for copyable diagnostics)
- `/api/settings` the usual parameters (including `ui_lang`, the interface language); `/api/providers` provider list (`/refresh` to update)
- `/api/stations_def` helper registration (the contents of `stations.json`)
- `/api/onboard/state`, `/api/onboard/progress` onboarding progress (step, played animations, half-filled forms; progress POST merges)
- `/api/stations/copy` (POST) duplicate a helper: config and key copied, name auto-incremented, takes the next free seat
- `/api/stations/delete` (POST) delete a helper; one with a running task answers busy without `confirm` and interrupts it with
- `/api/reset` (POST) reset everything: helpers, settings, keys, task records and logs; keeps `data/work`; needs `force` while tasks run
- `/api/shutdown` (POST) the core shuts itself down: same path as tray "Exit" (stops running workers, closes the database)
- `/api/tmp` how much the temp files take (`/api/tmp/clean` POST cleans)
- `/api/data` how big the data folder is and how much of it is run records (`/api/data/clean` POST compresses finished tasks' records now)
- `/api/efficiency` efficiency: time, turns and usage per task and per helper over the last days (`?days=7`); `dispatcher` / `goal` filters
- `/api/import_old` (POST) import from an old version: only after the old version has quit, and only while this box has no tasks
- `/api/connectors` supported clients; `/api/connectors/snippet` a paste-able connection snippet for one coding assistant (with the one-click link for Cursor and the install command for Claude Code / Codex)
- `/api/summon/<helper>` "How to give work": for a coding assistant, the install link / command and a wake-up text; for a check-in helper, the text to paste, where, and the steps
- `/api/capabilities` data for the Capabilities page: each switch's value, description, cost, results from the last 30 days, licenses
- `/api/office` data for the office scene
- `/api/health` liveness

### Repository layout

```
boxbox/      the core (app / store / dispatcher / watchdog / tokens / gates / office_feed / scenes)
             facades/ (mcp_stdio · cli · http — thin, stateless)
             runners/ (base · pi: run it with an API key · scheduled: check-in mode reading the exchange file)
             i18n_data/ (backend word lists, Chinese and English)
             static/  (home · tasks · helpers · capabilities · onboarding · settings · self-check, plus the i18n-*.js word lists)
             templates/ (the coding assistant's and the helper's manuals, each in Chinese and English)
assets/      icons and pixel art (original)
office/      the office scene (/office and the home-page embed)
static/tabler offline stylesheet (tabler.min.css for the home shell)
docs/        release notes for each version (release-*.md)
data/        runtime data: boxbox.db, stations.json, secrets.json, tasks/, logs/ (gitignored; next to the exe in exe mode)
tmp/         temp files: one folder per task, auto-cleaned (gitignored; next to the exe in exe mode)
```

## Known limitations

- Check-in mode: every check-in starts with no context; if the timer on your side never fires, the core can only nudge you.
- Your coding assistant lives in your own app; the box can't wake an idle chat there, only remind you with notifications and the tray.
- A note your coding assistant leaves for a working helper reaches it only when that round ends.
- Usage is measured only: check-in-mode helpers and your coding assistant's own usage aren't counted; "how much you saved" isn't shown yet.

A few more facts:

- The exe is a PyInstaller one-file build that unpacks to a temp folder on every start; a few antivirus products flag that.

## Development

```
python -m boxbox serve                   # run from source, then open http://127.0.0.1:8878
```

What changed in each version: [docs/release-0.6.md](docs/release-0.6.md) (0.6), [docs/release-0.5.md](docs/release-0.5.md) (0.5), [docs/release-0.4.md](docs/release-0.4.md) (0.4), [docs/release-0.3.md](docs/release-0.3.md) (0.3).

## License, privacy and security

- Code: MIT, see [LICENSE](LICENSE).
- Third-party components: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) (notes), [THIRD_PARTY_NOTICES.en.md](THIRD_PARTY_NOTICES.en.md) (the same notes in English) and [THIRD_PARTY_LICENSES.txt](THIRD_PARTY_LICENSES.txt) (full license texts of everything in the exe).
- Data and privacy: [PRIVACY.en.md](PRIVACY.en.md), [PRIVACY.md](PRIVACY.md). The exe's Settings under "Data & privacy" shows the same text, in the language of the interface.
- Keys: they live only in `data\secrets.json` (plain text, on this computer only); the page and the interface never show them.
- The box does not read the environment variables of your system as keys: only the copy in `data\secrets.json` counts.
- Security issues: report privately as described in [SECURITY.md](SECURITY.md).

## Notice

【Notice】agentboxbox uses the coding assistants already signed in on your computer. It does not copy or store any provider's sign-in credentials. Helpers call models with API keys you set up yourself. Your use of each service is subject to your agreement with that provider.

agentboxbox is an independent project and is not affiliated with, endorsed by, or sponsored by the coding assistants or model providers mentioned here. Product names are used only to describe compatibility.