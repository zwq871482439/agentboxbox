# agentboxbox (猫猫盒子)

[中文版](README.md)

**A pixel-cat office that lives on your own computer: one leader turns your work into task cards and hands them to a few worker cats; each delivery passes a mechanical check first, then the leader reviews it.**

It's for someone who already pays for one strong agent (Cursor, Claude Code or Codex) and wants it to act as the leader, delegating cards to cheaper helper models on the same project. Everything runs on your own machine with no account and no server; nothing leaves it except the requests a worker sends to the model provider you picked for it (see [PRIVACY.en.md](PRIVACY.en.md)). agentboxbox never changes the settings of your AI software.

Current state: 0.5.0 is the current release. The exe is Windows-only; the pages, the texts for your AI app and the office all speak Chinese and English. The language follows your system on first launch and you can switch it in the welcome window or in Settings. Worker cats have two ways to take work: running on an API key, or check-in mode (your AI app checks in on a timer).

## What it does

- the leader breaks work into **self-contained task cards** and assigns each to a station;
- when a station finishes, the delivery first passes **mechanical checks** (free), then the **dispatcher reviews** it;
- all the waiting is done by the box itself (delivery receipts, heartbeats, a watchdog) — models never poll;
- the home page shows everything at a glance: who in the office is busy and who is idle; the board shows every card, how long it has waited, what it cost.

Worker cats have two ways to take work (each station picks one):

| Way | How work arrives | Who it's for |
|---|---|---|
| Run it with an API key | One Pi process per card (provider, model, key); it exits when the card is done | Anyone with a pay-per-use API key |
| Check-in mode | Your AI app opens a new chat every few minutes to pick up a card from a file the box writes; no key, any app | People who work in an AI app |

The leader has exactly one home: a chat in the AI software you already use. The box talks to it through that software's tool interface (the address is in the paragraph you paste during onboarding). The box does not keep a leader of its own, and there is no "talk to the leader" entry: the leader always lives in your app. You can have several leaders: when two projects each have their own chat acting as leader, click "Add another leader" on the Stations page and give the new address to one of the chats. Each leader only sees and reviews the cards it dispatched; the cats are shared. If two chats are connected to the same leader, the box says so in its replies and on the Stations page.

## Installing

- **Requirements**: Windows 10 / 11, 64-bit. With the exe you don't need Python or Node — both are packed inside.
- **With the exe**: download `agentboxbox_<version>.exe` from https://github.com/zwq871482439/agentboxbox/releases (the release repo gets tagged, then the pipeline builds the exe, hashes it and attaches the release notes). Make a fresh folder for it, put the exe there and double-click. Two folders appear next to the exe: `data\` holds configuration and records (stations, keys, tasks, logs) — **don't delete it casually**; `tmp\` holds throw-away scratch from work in progress, cleared automatically when a card is done or cancelled — **safe to delete any time no card is running** (Settings has a one-click clean too). In `data\`, the run records of finished cards are compressed after a few days and deleted later; the number of days is under Advanced in Settings. Don't drop the exe into a crowded desktop or your downloads folder.
- **First launch**: pixel windows pop up over the office on the home page and walk you through hiring; a cat icon appears in the tray. The window's × only minimizes to the tray; to quit, right-click the tray cat and choose "Exit". Tick "Start with Windows" in the tray menu if you want it on login.
- **Uninstalling**: quit from the tray, then delete the folder. If you ever ticked "Start with Windows", untick it first (otherwise a shortcut stays in the Windows Startup folder). Windows keeps one registry entry for the tray icon's appearance; harmless. agentboxbox writes nothing into other software, so deleting the folder removes it all.
- **From source (developers)**: Python 3.11+, then `python -m boxbox serve` at the repo root and open `http://127.0.0.1:8878`.

### Upgrading

- **Simplest**: quit the old version from the tray, put the new exe in that same folder, and double-click. `data\` stays, so the cats, the settings and the cards are still there. Delete the old exe when you are done.
- **A new folder**: quit the old version from the tray first, open the new one, then use "Import from an old version" under Data and privacy in Settings. Give it the old folder, or the `data\` folder inside it. Do not copy `data\` while the old version is still open: cards assigned, handed back or accepted after that copy do not come along.

## Onboarding

On first launch, pixel windows pop up over the office and walk you through it in about ten minutes (close or refresh any time — the box remembers where you were):

1. **Welcome**: one line about what this is.
2. **Hire a leader**: pick a name and a look.
3. **Copy a paragraph into a new chat of your usual AI software** (Cursor, Claude Code, Codex, …): it's written for the AI, so paste it whole. The AI becomes your leader: it calls get_briefing for its manual, then reaches the box at the address in that paragraph and starts working. Once connected it may ask whether to add the box to its tool list — your call; **agentboxbox never touches the settings of any software on your machine**.
4. **Hire a worker cat**: name and look, then one way to get work — "run it with an API key" (provider, model, key; "Test connection" really asks the provider once) or "check-in mode" (no key needed). A failed test doesn't block hiring: the cat joins anyway, its cards queue, and work starts as soon as the endpoint answers.
5. **Assign your first card**: the last window hands you a copy-paste example ("Make me a card: …"). Send it in the leader's chat, or just tell the leader what you want and it will write the card.

The pages, the texts for your AI app and the office scene all follow the interface language. The language is decided on first launch from your system; a small "Chinese / English" switch in the welcome window changes it right away, and Settings has it later on.

Every new chat in your AI software needs that paragraph pasted again (the "Wake the leader" button on a station badge copies the same one).

## Everyday use

**The home page (`/`) is the office**: the top bar shows "Working / Success / Check" on the right, and the rest of the screen is the office scene.

- The scene carries a **day/night switch** (auto / dawn / day / dusk / night; auto follows the clock, cut-off times configurable in Settings) and two buttons, **Activity** and **Usage**, which open small pop-ups with a red dot for anything new.
- Next to the meeting-room projector stands a **party arcade**: click it for a small menu — play a movie, run a round, or send everyone back to work. The cats organize themselves too: nap breaks, late-night snacks, stand-ups, a celebration when a batch lands.
- **Click a cat for its details**: state, the card it's on, how many are queued behind, quota left, recent activity.
- Anything that needs you shows up in the strip above the scene; tray icon and top bar use the same severity levels, so you won't get a red dot here and a flash there.

**Desktop notifications**: the leader sits in your own app, and when that chat is idle the box cannot call it. So when a card comes back, does not run, never starts, gets stuck or waits for the leader, the box shows a system notification in the corner of your screen and asks you to say something in the chat. Switch it off in Settings ("A notification on your desktop when a card comes back or something goes wrong").

**Cat states**:

| State | Meaning |
|---|---|
| Working | Working ("Working · N queued" when more are waiting) |
| Idle | No work; ready for a card |
| On a break | Temporarily out: quota spent / rate-limited / endpoint unreachable / provider error. Shows why and when it will be back, and resumes on its own |
| Disabled | You switched it off by hand; it stays off |

**What "queued" tells you**: a queued card says exactly what it's waiting for — the cat to finish its current card, the cat to come back from its break, or the model API to become reachable again. One cat works one card at a time; to run more cards at once with the same provider, hire more cats (or click "Copy" on a badge). A card stopped before it started reads "never started" rather than "failed"; the leader can reassign or drop it.

**A card cut off by an API error**: when a worker cat hits a model API error halfway through (cannot reach it, rate limited, server error), the card is not a failure and it is not lost: the cat goes on a break, the card goes back into the queue and waits for it, and when the cat comes back it carries on in the same conversation. The same card gets three such automatic continuations; after that it counts as "interrupted" and you and the leader decide what to do.

**Interrupted cards** (cut off by a quit or crash) come back as a question on your next visit to the home page: resume the same conversation, hand them to the leader, or leave them be.

**Stations (`/stations`)**: badge cards on lanyards, seven fixed seats — the leader plus worker cats A–F. Click a badge for its drawer (how it gets work, whether it's connected, today's work, recent dispatching, quota left); badges offer "Copy" (copies configuration and key, auto-names, gets its own work directory), "Delete" (asks twice if a card is running; confirming interrupts that card) and "Change settings" (change look, name or way of taking work; the leader can only change its look).

**Quota check**: three coding plans are recognized out of the box — Kimi Code membership, Zhipu GLM Coding Plan and MiniMax Token Plan (fill in the address of one of them and the box picks how to check); for anyone else, pick "Custom" in the station settings and fill in the query address and the path of the used percentage in the reply. The result shows in the station detail and in the board's "usage" table.

**Board (`/board`)**: every card from assignment to review; one row per station (state word, current card, minutes); card details include measured usage.

**Settings (`/settings`)**: box settings (language, how often you are nudged, desktop notifications, provider list, day and night in the office), data & privacy, temp-file cleanup, and "Reset everything" at the bottom (two confirmations, then onboarding starts over).

When something looks wrong, start with "Check" in the top bar (each failed item says what to do) or the check page (`/doctor`) and its "Copy the diagnostics" (paths and keys are masked; read it once more before posting an issue). What changed in 0.4 is in [`docs/release-0.4.md`](docs/release-0.4.md); coming from 0.2, read the "Known issues" at the end of [`docs/release-0.3.md`](docs/release-0.3.md) first.

## For developers

Commands, concepts, endpoints and the repository layout. You don't need this section for everyday use.

### Command reference

Every command takes `--lang zh|en` to pick the language of its output (without it, the command follows the language of the box).

| Command | What it does |
|---|---|
| `python -m boxbox serve [--port 8878]` | Start the core (HTTP + watchdog + SQLite); listens on 127.0.0.1 only |
| `python -m boxbox tray [--show] [--port 8878]` | Tray shell: tray icon + embedded window (needs `pip install pystray pywebview`); double-clicking the exe equals `tray --show` |
| `python -m boxbox mcp --station <station> --core <URL>` | MCP stdio facade, for clients that don't accept a `url` by hand. Everything the box hands out writes only `http://127.0.0.1:8878/mcp?station=<station>`, so clients connect straight to the core and spawn nothing |
| `python -m boxbox doctor [--json] [--no-core]` | Self-check: core / data dir / leader / Pi / templates |
| `python -m boxbox board` | Board: one row per station |
| `python -m boxbox todo` | The leader's to-do: awaiting review, stuck, idle stations |
| `python -m boxbox task <id>` | Everything about one task card |
| `python -m boxbox wait [--timeout 600] [--station <leader>] [--port 8878]` | Wait for a card to come back: prints new events (exit 0), nothing came (2), core not running (3) |
| `python -m boxbox report --task <id> --status done --summary "..."` | Worker report (heartbeat / done / blocked / issue) |
| `python -m boxbox assign --station <station> --card card.json` | Assign a card (normally the leader does this via assign) |
| `python -m boxbox review --task <id> --verdict accept --note "..."` | Review: accept, or return (re-dispatch next round) |

If a core is already listening on the port, `tray` (and double-clicking the exe) attaches to it instead of starting another.

### Concepts

| Concept | Meaning |
|---|---|
| Station | One seat: its name + how it takes work (run it with an API key / check-in mode) |
| Leader | The main-model station: writes cards, assigns (assign), reviews (review). Exactly one; registering another one replaces the old one |
| Worker cat | A helper-model station: takes cards, does the work, reports (report). No assigning rights |
| Task card | The only unit of dispatch, **self-contained** (a fresh chat has no old context): `goal` / `inputs` / `expected_output{kind,path}` / `acceptance{review}` are all required; assign rejects the card without them |
| Checks | Mechanical checks run on every delivery first (exists / headings / command / commits / json / size); free; any failure returns the card without bothering the leader. The card field is still `acceptance.gates` |
| Review | Whoever assigns, reviews: after the checks pass, the dispatcher decides (or leaves it to the user, or "checks passing is enough") |
| Way of taking work | How a cat takes work: `once` (one Pi process per card) / `scheduled` (check-in mode: reads the exchange file); the leader is `manual` |
| Language | The interface language lives in the setting `ui_lang` (zh / en) and falls back to the system language when it is not set; the page word lists are in `boxbox/static/i18n-*.js`, the backend ones in `boxbox/i18n_data/` |

### Pages and endpoints

Pages (all under `http://127.0.0.1:8878`):

- `/` home (the office scene): top bar + full-screen office; day/night switch, Activity and Usage buttons and the party arcade live inside the scene; click a cat for details; **onboarding happens here, window by window**
- `/board` board: stations (with model, quota and when a resting cat is back), to-do, task cards, usage, efficiency (time and usage per card and per cat)
- `/stations` stations: badge cards (leader + A–F); click one for its drawer; copy, delete and change settings on the badge; "Add another leader"
- `/settings` settings: box settings, data & privacy (temp files, how big the data folder is, import from an old version), advanced (stuck alerts, how run records are kept), reset everything
- `/doctor` self-check: per-item results, what to do, copy the diagnostics
- `/office` the office scene on its own (the home page embeds this one)
- `/onboard` old address; just redirects home

Endpoints (GET is read-only; writes accept same-origin local requests only; `/mcp?station=<station>` and `/rpc/<tool>` speak JSON-RPC for models):

- `/api/meta` top-bar data: running count, success rate, alerts
- `/api/stations` per station: state word, current card, minutes, seat
- `/api/stations/detail` station detail (config without the key + connection + dispatch log + quota)
- `/api/tasks` the task board (`?state=` filter), each card with its queue reason
- `/api/tasks/<id>` everything about one card: card, runs, raw report, measured usage
- `/api/todo` to-do: awaiting review, stuck, returned-pending, interrupted, never-started, failed, idle stations
- `/api/interrupted` cards interrupted by the last quit or crash (POST `/resume` to continue, `/dismiss` to leave them)
- `/api/timeline` recent runs and events
- `/api/tokens` measured usage (only what can be measured exactly; stations without an API read "not counted")
- `/api/doctor` self-check results (JSON; `?text=1` for copyable diagnostics)
- `/api/settings` the usual parameters (including `ui_lang`, the interface language); `/api/providers` provider list (`/refresh` to update)
- `/api/stations_def` station registration (the contents of `stations.json`)
- `/api/onboard/state`, `/api/onboard/progress` onboarding progress (step, played animations, half-filled forms; progress POST merges)
- `/api/stations/copy` (POST) duplicate a worker cat: config and key copied, name auto-incremented, takes the next free seat
- `/api/stations/delete` (POST) delete a station; one with a running card answers busy without `confirm` and interrupts it with
- `/api/reset` (POST) reset everything: stations, settings, keys, task records and logs; keeps `data/work`; needs `force` while cards run
- `/api/shutdown` (POST) the core shuts itself down: same path as tray "Exit" (stops running workers, closes the database)
- `/api/tmp` how much the temp files take (`/api/tmp/clean` POST cleans)
- `/api/data` how big the data folder is and how much of it is run records (`/api/data/clean` POST compresses finished cards' records now)
- `/api/efficiency` efficiency: time, turns and usage per card and per cat over the last days (`?days=7`)
- `/api/import_old` (POST) import from an old version: only after the old version has quit, and only while this box has no cards
- `/api/connectors` supported clients; `/api/connectors/snippet` a paste-able connection snippet for one station
- `/api/summon/<station>` "wake the leader": the paragraph to paste, where, and the steps, per way of taking work
- `/api/office` data for the office scene
- `/api/health` liveness

### Repository layout

```
boxbox/      the core (app / store / dispatcher / watchdog / tokens / gates / office_feed / scenes)
             facades/ (mcp_stdio · cli · http — thin, stateless)
             runners/ (base · pi: run it with an API key · scheduled: check-in mode reading the exchange file)
             i18n_data/ (backend word lists, Chinese and English)
             static/  (home · board · stations · onboarding · settings · self-check, plus the i18n-*.js word lists)
             templates/ (the leader's and the worker cat's manuals, each in Chinese and English)
packaging/   build scripts (build_exe.ps1 → one-file agentboxbox_<version>.exe, Node and Pi bundled)
assets/      icons and pixel art (original)
office/      the office scene (/office and the home-page embed)
static/tabler offline stylesheet (tabler.min.css for the home shell)
docs/        release notes for each version (release-*.md)
data/        runtime data: boxbox.db, stations.json, secrets.json, tasks/, logs/ (gitignored; next to the exe in exe mode)
tmp/         temp files: one folder per card, auto-cleaned (gitignored; next to the exe in exe mode)
```

## Known limitations

- Check-in mode: every check-in starts with no context; if the timer on your side never fires, the core can only nudge you.
- A Cursor IDE leader can't be woken from outside — tray dot plus a "wake the leader" hint; IDE chats and CLI chats don't share state.
- Usage is measured only: check-in-mode cats and a Cursor IDE leader aren't counted; "how much you saved" isn't shown yet.

A few more facts:

- The exe is a PyInstaller one-file build that unpacks to a temp folder on every start; a few antivirus products flag that.

## Development

```
python -m boxbox serve                   # run from source, then open http://127.0.0.1:8878
pwsh packaging/build_exe.ps1             # package → dist/agentboxbox_<version>.exe (needs pip install pyinstaller pystray pywebview)
```

What changed in each version: [docs/release-0.5.md](docs/release-0.5.md) (0.5), [docs/release-0.4.md](docs/release-0.4.md) (0.4), [docs/release-0.3.md](docs/release-0.3.md) (0.3).

## License, privacy and security

- Code: MIT, see [LICENSE](LICENSE).
- Third-party components: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) (notes), [THIRD_PARTY_NOTICES.en.md](THIRD_PARTY_NOTICES.en.md) (the same notes in English) and [THIRD_PARTY_LICENSES.txt](THIRD_PARTY_LICENSES.txt) (full license texts of everything in the exe).
- Data and privacy: [PRIVACY.en.md](PRIVACY.en.md), [PRIVACY.md](PRIVACY.md). The exe's Settings under "Data & privacy" shows the same text, in the language of the interface.
- Keys: they live only in `data\secrets.json` (plain text, on this computer only); the page and the interface never show them.
- The box does not read the environment variables of your system as keys: only the copy in `data\secrets.json` counts.
- Security issues: report privately as described in [SECURITY.md](SECURITY.md).