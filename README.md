# Social Agents

Automated research, content creation, scheduling and posting for many X/Twitter and Instagram accounts at once.
Everything runs in Docker and is controlled from a web admin panel.

You give it a list of accounts and a topic for each. For every account it runs its own agent that:

1. researches the topic (latest news, recent B2B offers, trending topics, viral posts, viral content),
2. writes posts from that research,
3. finds a Pinterest image for each post,
4. schedules the posts into that account's posting times and writes them to a Google Sheet,
5. publishes each post to the account when its time arrives.

---

## Contents

1. [What has and has not been tested](#1-what-has-and-has-not-been-tested)
2. [Requirements](#2-requirements)
3. [Install and run](#3-install-and-run)
4. [Configuration file (.env)](#4-configuration-file-env)
5. [First-time setup](#5-first-time-setup)
6. [The admin panel](#6-the-admin-panel)
7. [Google Sheets](#7-google-sheets)
8. [Posting credentials](#8-posting-credentials)
9. [How the system works](#9-how-the-system-works)
10. [Statuses](#10-statuses)
11. [Data storage](#11-data-storage)
12. [Security](#12-security)
13. [AI providers](#13-ai-providers)
14. [API reference](#14-api-reference)
15. [Project structure](#15-project-structure)
16. [Operations](#16-operations)
17. [Troubleshooting](#17-troubleshooting)
18. [Known limitations](#18-known-limitations)

---

## 1. What has and has not been tested

| Part | State |
|---|---|
| Containers build and start, panel login | Tested, works |
| Add / edit / delete account, encrypted credential storage | Tested, works |
| Start, pause, resume, stop, run now | Tested, works |
| Research collection (Google News + DuckDuckGo) | Tested with a real topic, about 50 items per cycle |
| Pinterest image search | Tested, returns real pins |
| Content writing, scheduling, approval, publish step | Tested only against a fake local AI server |
| Real NVIDIA API call | **Not tested** (no key was available) |
| Google Sheets read and write | **Not tested** (no service account was available) |
| Real posting to X and Instagram | **Not tested** (no account credentials were available) |
| Pinterest video search | Tested, **returns nothing** (see limitations) |

Use the two test buttons in Settings to check the NVIDIA and Google Sheets connections before starting agents,
and keep accounts in approval mode until you have seen a few real posts go out correctly.

---

## 2. Requirements

- Docker with Docker Compose v2 (Docker Desktop on macOS/Windows, or Docker Engine on Linux).
- `openssl` on the host (only used once by `setup.sh`).
- An NVIDIA API key from https://build.nvidia.com (or a key for another supported provider).
- Optional: a Google Cloud service account for Google Sheets.
- Per account you want to post from: X developer app keys, or an Instagram Graph API token.

---

## 3. Install and run

```sh
./setup.sh                      # first time only: creates .env and prints the admin password
docker compose up -d --build    # build the image and start both containers
```

Open **http://localhost:8080** and sign in with the `ADMIN_PASSWORD` value from `.env`.

Two containers start from the same image:

| Container | Command | Job |
|---|---|---|
| `web` | `uvicorn app.web:app` | Admin panel and JSON API on port 8080 |
| `worker` | `python -m app.master` | Master agent plus one agent per account |

Both mount the same Docker volume (`data`) at `/data`. The panel never talks to the worker directly: it writes
what you want (start, pause, stop) into the shared database and the worker obeys it within a few seconds.
Restarting `web` does not interrupt running agents.

---

## 4. Configuration file (.env)

Created by `setup.sh`. It is never copied into the Docker image and is ignored by git.

| Variable | Default | Meaning |
|---|---|---|
| `MASTER_KEY` | random 64 hex chars | Encrypts every stored API key and credential. Must be 16+ characters. **Back it up.** If it changes or is lost, saved secrets cannot be decrypted and must be entered again. |
| `ADMIN_PASSWORD` | random | Password for the admin panel. Change it here and restart `web`. |
| `PANEL_PORT` | `8080` | Host port for the panel (bound to 127.0.0.1 only). |
| `LLM_CONCURRENCY` | `3` | Maximum parallel AI requests across all agents. Lower it if you hit rate limits. |
| `GRAPH_API_VERSION` | `v23.0` | Facebook Graph API version used for Instagram. Raise it when Meta retires this version. |

After editing `.env`, apply it with `docker compose up -d`.

---

## 5. First-time setup

1. **AI provider** - Settings page: paste the NVIDIA API key, press **Save settings**, then **Test AI provider**.
   A green "OK" reply means the key, model and URL work.
2. **Google Sheets (optional)** - see [section 7](#7-google-sheets). Without it, add accounts by hand in the panel;
   everything except the sheet mirror still works.
3. **Accounts** - press **Add account** on the Dashboard, or put rows in the master sheet and press **Sync sheet now**.
4. **Credentials** - on each account row press **Add keys** and enter that account's posting credentials
   ([section 8](#8-posting-credentials)). Research and content creation work without them; only publishing needs them.
5. **Start** - press **Start** on an account, or **Start all**. The first cycle begins immediately.
6. **Approve** - open the Content page, review the posts and press **Approve**. Approved posts publish at their
   scheduled time.

---

## 6. The admin panel

The sidebar on the left switches between five pages. At the bottom it shows whether the master agent (the
`worker` container) is online, and the Sign out button. The Content item shows a yellow counter with the number
of posts waiting for approval.

### Dashboard

- **Stat cards**: accounts, agents running, posts pending approval, scheduled, posted, failed (totals over all accounts).
- **All agents bar**:
  - **Start all / Pause all / Resume all / Stop all** apply the command to every account.
  - **Sync sheet now** makes the master agent read the master sheet on its next tick (within 3 seconds).
  - **Add account** opens the account form.
  - The text beside the title shows the time and result of the last sheet sync.
- **Agent table**, one row per account:
  - *Account*: handle, platform, where it came from (`panel` or `sheet`), posting mode.
  - *Topic*: topic, posting times and timezone.
  - *Agent*: live status and the step it is on right now; the last error in red if the last cycle failed.
  - *Cycle*: when the last research-and-create cycle ran and when the next one is due.
  - *Posts*: counts of pending, scheduled, posted and failed posts.
  - *Controls*:

| Button | Shown when | Effect |
|---|---|---|
| Start | agent is stopped | Starts the agent. A cycle runs immediately if one is due. |
| Pause | agent is running | Freezes the agent at its next step. Nothing is researched, written or posted while paused. |
| Resume | agent is paused | Continues exactly where it paused. |
| Run now | agent is running | Runs a research-and-create cycle now instead of waiting for the next one. |
| Stop | agent is running or paused | Ends the agent. A cycle in progress is abandoned and starts over on the next Start. |
| Edit | always | Opens the account form. |
| Add keys / Keys ✓ | always | Opens the credentials form. The tick means something is saved. |
| Delete | always | Stops the agent and permanently removes the account and its whole database. |

The page refreshes itself every 4 seconds.

#### Account form fields

| Field | Default | Meaning |
|---|---|---|
| Platform | X / Twitter | `twitter` or `instagram`. |
| Handle | required | Account username, with or without `@`. Platform + handle must be unique. |
| Topic | required | What the account is about. Drives all research and writing. |
| Tone | empty | Writing voice, e.g. "witty, expert". Empty means "confident, helpful, conversational". |
| Language | English | Language the posts are written in. |
| Post times | `09:00,13:00,18:00` | Daily posting slots, 24-hour `HH:MM`, comma separated, in the account's timezone. |
| Timezone | your browser's | IANA name such as `Asia/Dhaka`, `America/New_York`, `UTC`. |
| Research + create every (hours) | 24 | Length of one cycle, 1 to 168. |
| Posting | I approve each post first | `approval`: posts wait for you. `auto`: posts publish without review. |
| Own schedule sheet | empty | A separate schedule spreadsheet for this account; overrides the one in Settings. |

### Content

Pick an account and, if you want, a status filter. Each row shows the image (click to open), a link to the
Pinterest pin and to the research source, the post text and hashtags, the scheduled time, and the status.

| Button | Shown for | Effect |
|---|---|---|
| Approve | pending approval | Marks the post scheduled. If its time has already passed it publishes within 30 seconds. |
| Reject | pending approval | Discards the post. Its slot becomes free and is refilled on the next cycle. |
| Hold | scheduled | Sends the post back to pending approval. |
| Post now | failed, missed, rejected | Schedules the post for right now. |
| Edit | everything not yet posted | Change text, hashtags, image URL, video URL and scheduled time. |
| Approve all pending | top bar | Approves every pending post of the selected account after a confirmation. |

Every change here is also written to the schedule sheet.

### Research

Pick an account to see its latest cycle: the AI-written brief (a summary plus 8 to 12 content angles), the raw
findings grouped into the five categories with links, and the last 20 cycles with their result.

### Logs

The newest 200 events, for all accounts or one. Each event shows the time, account, which agent wrote it
(`master`, `agent`, `research`, `media`, `scheduler`, `publisher`, `panel`) and the message. Warnings are
yellow, errors red. The log keeps the most recent 5,000 events.

### Settings

- **AI provider**: provider preset, API key, optional model and base URL overrides. "In use" shows the values
  that will actually be used.
- **Google Sheets**: service account key, master accounts sheet, content schedule sheet, sync interval in
  minutes (default 5), and whether accounts newly found in the sheet start automatically (default yes).
- **Save settings**, **Test AI provider**, **Test Google Sheets**.

Secret fields (API key, service account key) are never sent back to the browser. Leave them blank to keep the
saved value.

---

## 7. Google Sheets

### 7.1 Create the service account (once)

1. Go to https://console.cloud.google.com and create or pick a project.
2. *APIs & Services → Library*: enable **Google Sheets API**.
3. *APIs & Services → Credentials → Create credentials → Service account*. Give it any name and finish.
4. Open the service account → *Keys → Add key → Create new key → JSON*. A `.json` file downloads.
5. In the panel, Settings → paste the whole content of that file into **Service account key** and save.
   The panel then shows the service account email.
6. Open each Google Sheet you want to use → **Share** → add that email as **Editor**.

### 7.2 Master accounts sheet (input)

The master agent reads the **first tab**. Row 1 is the header. Column names are not case sensitive and the
order does not matter. Only `account` and `topic` are required.

| Column | Other accepted names | Meaning |
|---|---|---|
| `account` | handle, username, account name, name | Account handle. Required. |
| `topic` | niche, account topic | Account topic. Required. |
| `platform` | network | `twitter`, `x`, `instagram` or `ig`. Empty means twitter. `twitter, instagram` creates two accounts. |
| `tone` | voice | Writing voice. |
| `language` | | Post language. |
| `post_times` | post times, times | e.g. `09:00,13:00,18:00`. |
| `timezone` | time zone, tz | e.g. `Asia/Dhaka`. |
| `cycle_hours` | cycle hours | 1 to 168. |
| `post_mode` | post mode, mode | `approval` or `auto`. |
| `schedule_sheet` | schedule sheet, schedule_sheet_id | Own schedule spreadsheet for this account. |

Example:

| account | platform | topic | tone | post_times | timezone | post_mode |
|---|---|---|---|---|---|---|
| @aitools_daily | twitter, instagram | AI tools for small business | witty | 09:00,13:00,18:00 | Asia/Dhaka | approval |
| @saas_growth | twitter | B2B SaaS growth | expert | 10:00,16:00 | America/New_York | auto |

Sync rules:

- The sheet is read every *sync interval* minutes and whenever you press **Sync sheet now**.
- A row whose platform + handle is new creates an account. It starts automatically unless you turned that off in Settings.
- A row that matches an existing account updates that account's fields from the sheet. Empty cells change nothing.
- Removing a row does **not** delete or stop the account. Delete accounts in the panel.
- A row with an invalid value (bad timezone, bad time) is skipped and reported in Logs.
- Credentials are never read from the sheet. Enter them in the panel.

### 7.3 Content schedule sheet (output)

Put the spreadsheet link in Settings → **Content schedule sheet**. The scheduler creates one tab per account,
named `platform-handle`, with this header:

| Column | Content |
|---|---|
| `id` | `<account id>-<post id>`, used to find the row again |
| `account` | handle |
| `platform` | twitter or instagram |
| `scheduled_at` | posting time in the account's timezone, `YYYY-MM-DD HH:MM` |
| `status` | see [section 10](#10-statuses) |
| `text` | post body |
| `hashtags` | hashtags |
| `image_url` | Pinterest image link |
| `video_url` | Pinterest video link (currently always empty) |
| `pinterest_source` | link to the pin page |
| `posted_url` | link to the published post |
| `updated_at` | last update time (UTC) |

Rows are added when posts are scheduled and updated whenever a post's status or content changes. The sheet is
a one-way mirror: editing it has no effect on the system. If the sheet cannot be written, the agent logs a
warning and carries on; the post is still saved and published.

---

## 8. Posting credentials

Entered per account with **Add keys**. They are encrypted and stored in that account's own database. The form
only ever shows the last four characters of a saved value.

### X / Twitter

1. Create a project and app at https://developer.x.com.
2. In the app's *User authentication settings* set permissions to **Read and write**.
3. In *Keys and tokens* generate, **after** setting the permission:

| Field in the panel | Name in the X portal |
|---|---|
| `api_key` | API Key (Consumer Key) |
| `api_secret` | API Key Secret (Consumer Secret) |
| `access_token` | Access Token |
| `access_token_secret` | Access Token Secret |

The access token must belong to the account you want to post from. Your X API plan's posting limits apply.
If the image cannot be downloaded or uploaded (limit 5 MB), the tweet is posted as text only and a warning is logged.

### Instagram

Needs an Instagram **Business or Creator** account linked to a Facebook Page, and a Meta developer app with the
`instagram_content_publish` permission.

| Field in the panel | Meaning |
|---|---|
| `ig_user_id` | The Instagram account's numeric Graph API user ID |
| `access_token` | A long-lived access token with publish permission |

Instagram posts must have an image, and the image must be a public JPEG URL. Long-lived tokens expire after
about 60 days; replace the token in the panel when posting starts failing with a token error.

---

## 9. How the system works

```
                 ┌──────────────── Docker volume /data ────────────────┐
 browser ──► web │ control.db              accounts/account_<id>.db    │ worker
        (panel + │ accounts, settings,     credentials, research,      │ (master agent)
           API)  │ desired state, events   briefs, posts, runs         │   ├─ agent: account 1
                 └─────────────────────────────────────────────────────┘   ├─ agent: account 2
                                                                           └─ agent: account N
 each account agent:  research → content → media → scheduler  (one cycle)   +   publisher (every 30 s)
```

### Master agent

Every 3 seconds it:

1. writes a heartbeat (the panel shows "offline" if this is older than 20 seconds),
2. syncs the master sheet if the interval has passed or a sync was requested,
3. starts an agent for every account that should be running or paused and has none,
4. removes accounts you deleted, once their agent has stopped.

Each account agent is a separate thread, so all accounts work in parallel. On a worker restart every agent that
was running or paused comes back automatically; a cycle that was in progress is marked `interrupted` and run again.

### Account agent loop

Every 5 seconds the agent checks whether a cycle is due (first start, the cycle interval has passed, or you
pressed Run now). Every 30 seconds it runs the publisher. Between every step it checks for pause and stop.

### One cycle

1. **Find free slots.** Posting slots from 5 minutes from now until `cycle hours + 6 hours` ahead that do not
   already have a pending, scheduled or posted post. At most 30. If there are none, the cycle ends without
   doing research.
2. **Research agent.** Two searches for each of the five categories, limited to the last 7 days:

   | Category | Sources |
   |---|---|
   | Latest news | Google News, DuckDuckGo News |
   | Recent B2B offers | Google News (partnership / deal / enterprise / launch), DuckDuckGo |
   | Trending topics | DuckDuckGo, Google News |
   | Viral posts | DuckDuckGo limited to x.com, reddit.com, linkedin.com; DuckDuckGo "most shared" |
   | Viral content | DuckDuckGo video search sorted by views, DuckDuckGo |

   All findings are saved. The AI then turns them into a brief: a summary and 8 to 12 content angles. A source
   that fails is logged as a warning and skipped.
3. **Content agent.** The AI writes one post per free slot from the brief, in the account's language and tone.
   It is given the last 20 posts so it does not repeat itself and is told not to invent facts.
   - X: body plus hashtags is forced to fit 280 characters (hashtags are dropped first, then the body is cut).
   - Instagram: a short multi-line caption with 6 to 10 hashtags.
4. **Media agent.** For each post it searches Pinterest for the post's visual phrase and saves the image link
   and the pin link. It never reuses an image the account has already used.
5. **Scheduler agent.** Assigns each post to a slot, saves it in the account database, and writes the rows to
   the schedule sheet. Status is `pending_approval` in approval mode, `scheduled` in auto mode.

Then the next cycle is set for `cycle hours` later. If a cycle fails, it is retried after 30 minutes and the
error is shown on the Dashboard.

### Publisher agent

Every 30 seconds, for scheduled posts whose time has come:

- posts **one** post per run, so a backlog never goes out as a burst;
- a post more than 12 hours overdue (the agent was stopped or paused) is marked `missed` instead of being posted late;
- on success saves the link to the live post; on failure marks the post `failed` with the reason (it is not
  retried automatically, use **Post now**);
- updates the schedule sheet.

### AI calls

Requests to the AI provider are limited to `LLM_CONCURRENCY` at a time across all agents. A rate-limit or
server error is retried up to 4 times with increasing waits (4, 8, 16, 32 seconds).

---

## 10. Statuses

**Agent** (Dashboard)

| Status | Meaning |
|---|---|
| stopped | No agent is running for this account. |
| idle | Agent is running and waiting for the next cycle or the next post time. |
| working | Agent is in the middle of a step; the step is shown underneath. |
| paused | Agent is frozen until you press Resume. |
| error | Something unexpected failed; the agent retries by itself after 60 seconds. |
| starting… / pausing… / stopping… | Your command is waiting for the agent to reach its next step. |
| worker offline | The `worker` container is not running. |

**Post** (Content page and schedule sheet)

| Status | Meaning |
|---|---|
| pending_approval | Written and scheduled, waiting for your approval. |
| scheduled | Will be published at its scheduled time. |
| posted | Published; a link to the post is saved. |
| failed | Publishing was attempted and failed; the reason is shown. |
| missed | Its time passed by more than 12 hours while the agent was not running. |
| rejected | You discarded it. |

**Cycle** (Research page): `running`, `done`, `failed`, `stopped` (you stopped the agent mid-cycle),
`interrupted` (the worker restarted mid-cycle).

---

## 11. Data storage

Everything lives in the Docker volume `twitter_automation_n8n_data`, mounted at `/data`.

**`/data/control.db`** - shared control database

| Table | Content |
|---|---|
| `accounts` | One row per account: its settings, the state you asked for, the live agent status, current step, last error, cycle times. |
| `settings` | AI provider settings, Google Sheets settings, master heartbeat and last sync result. Secrets are encrypted. |
| `events` | The activity log. |

**`/data/accounts/account_<id>.db`** - one database per account, deleted with the account

| Table | Content |
|---|---|
| `credentials` | That account's posting credentials, encrypted. |
| `runs` | One row per cycle with start, finish, result and error. |
| `research` | Every research finding: category, title, summary, link, source, score. |
| `briefs` | The AI brief of each cycle. |
| `posts` | Every post: text, hashtags, image/video/pin links, source link, scheduled time, status, live post link, error. |

All databases are SQLite. All times are stored in UTC.

---

## 12. Security

- **Encryption at rest.** The AI API key, the Google service account key and every account credential are
  encrypted (Fernet: AES-128-CBC with HMAC-SHA256) with a key derived from `MASTER_KEY`. Reading a database
  file without `.env` reveals no secrets.
- **Isolation.** Each account's credentials are only in that account's own database file.
- **Panel access.** One admin password, a signed session cookie valid for 7 days, `SameSite=Strict`.
  Failed logins are delayed by one second. Every API route requires the session.
- **Network.** The panel port is bound to `127.0.0.1` only, so it is not reachable from other machines.
  There is no HTTPS. To use it from another machine, put a reverse proxy with TLS in front of it
  (Caddy, nginx, Cloudflare Tunnel) rather than changing the port binding.
- **Secrets never leave the server.** The API returns only "saved / not saved" and the last four characters.
- **Containers** run as a non-root user.
- Keep `.env` private and backed up. Do not commit it.

---

## 13. AI providers

Any service with an OpenAI-compatible `/chat/completions` endpoint works.

| Preset | Base URL | Default model |
|---|---|---|
| `nvidia` (default) | `https://integrate.api.nvidia.com/v1` | `meta/llama-3.3-70b-instruct` |
| `openai` | `https://api.openai.com/v1` | `gpt-4o-mini` |
| `openrouter` | `https://openrouter.ai/api/v1` | `meta-llama/llama-3.3-70b-instruct` |
| `groq` | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |
| `custom` | you enter it | you enter it |

To switch: Settings → choose the provider, paste its API key, optionally set a model, save, and press
**Test AI provider**. To use a different NVIDIA model, keep the `nvidia` preset and type the model name from
build.nvidia.com into **Model**. To add a preset permanently, add one line to `PRESETS` in `app/llm.py` and rebuild.

One provider is used for all accounts.

---

## 14. API reference

The panel is a client of this JSON API, so anything the panel does can be scripted. All routes except login
need the session cookie. Errors return `{"detail": "message"}`.

| Method | Path | Body | Purpose |
|---|---|---|---|
| POST | `/api/login` | `{"password"}` | Sign in, sets the session cookie |
| POST | `/api/logout` | | Sign out |
| GET | `/api/overview` | | Master status and every account with status and post counts |
| POST | `/api/master/action` | `{"action"}`: `start_all`, `pause_all`, `resume_all`, `stop_all`, `sync_sheet` | Control all agents |
| POST | `/api/accounts` | account fields | Create an account |
| PUT | `/api/accounts/{id}` | account fields | Edit an account |
| DELETE | `/api/accounts/{id}` | | Delete an account and its database |
| POST | `/api/accounts/{id}/action` | `{"action"}`: `start`, `pause`, `resume`, `stop`, `run_now` | Control one agent |
| GET | `/api/accounts/{id}/credentials` | | Which credential fields are saved |
| PUT | `/api/accounts/{id}/credentials` | credential fields, or `{"clear": true}` | Save or remove credentials |
| GET | `/api/accounts/{id}/posts?status=` | | List up to 300 posts |
| PATCH | `/api/accounts/{id}/posts/{post_id}` | any of `text`, `hashtags`, `image_url`, `video_url`, `scheduled_at`, `action` (`approve`, `reject`, `unapprove`, `retry`) | Edit or act on a post |
| GET | `/api/accounts/{id}/research` | | Latest brief, its findings, last 20 cycles |
| GET | `/api/events?account_id=&limit=` | | Activity log |
| GET | `/api/settings` | | Current settings (no secrets) |
| PUT | `/api/settings` | setting fields | Save settings |
| POST | `/api/settings/test-llm` | | Test the AI provider |
| POST | `/api/settings/test-sheets` | | Test reading the master sheet |

Example:

```sh
curl -c cookies.txt -X POST localhost:8080/api/login -H 'Content-Type: application/json' -d '{"password":"..."}'
curl -b cookies.txt -X POST localhost:8080/api/accounts/1/action -H 'Content-Type: application/json' -d '{"action":"pause"}'
```

---

## 15. Project structure

```
docker-compose.yml     the two services and the data volume
Dockerfile             Python 3.12 image, non-root user
requirements.txt       Python dependencies
setup.sh               creates .env
.env                   secrets and settings (created by setup.sh, not in git)
app/
  config.py            reads .env values
  crypto.py            encryption of stored secrets
  db.py                database schema, account validation, settings, credentials, event log
  llm.py               AI provider presets and the chat call with retries
  master.py            master agent: sheet sync and agent supervision (worker entrypoint)
  account_agent.py     per-account agent: loop, cycle, pause/resume/stop handling
  research.py          research agent: sources and brief
  content.py           content agent: post writing and length rules
  media.py             media agent: Pinterest search
  scheduler.py         scheduler agent: posting slots and saving the schedule
  publisher.py         publisher agent: X and Instagram posting
  sheets.py            Google Sheets reading and writing
  web.py               admin panel API
  static/index.html    admin panel UI (single file)
```

---

## 16. Operations

```sh
docker compose ps                       # are both containers running?
docker compose logs -f worker           # live agent activity
docker compose logs -f web              # panel requests and errors
docker compose restart worker           # restart all agents (they resume by themselves)
docker compose down                     # stop everything, data is kept
docker compose up -d --build            # start again / apply code changes
```

**Backup** (databases plus the key that decrypts them):

```sh
docker run --rm -v twitter_automation_n8n_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/social-agents-data.tgz -C /data .
cp .env env-backup.txt
```

**Restore**: put `.env` back, then

```sh
docker compose down
docker run --rm -v twitter_automation_n8n_data:/data -v "$PWD":/backup alpine \
  sh -c "rm -rf /data/* && tar xzf /backup/social-agents-data.tgz -C /data"
docker compose up -d
```

**Change the admin password**: edit `ADMIN_PASSWORD` in `.env`, then `docker compose up -d`.

**Erase everything** (all accounts, posts and saved credentials, cannot be undone): `docker compose down -v`.

---

## 17. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Sidebar shows "Master agent offline" | The `worker` container is down. `docker compose ps`, then `docker compose logs worker`. |
| Container exits with "MASTER_KEY ... must be set" | `.env` is missing. Run `./setup.sh`. |
| Row shows "LLM API key is not set" | Add the key in Settings. The cycle retries by itself within 30 minutes, or press Run now. |
| "request failed - HTTP 401" from the AI provider | Wrong API key. |
| "request failed - HTTP 404" from the AI provider | Wrong model name or base URL. |
| "request failed - HTTP 429" | Rate limit. Lower `LLM_CONCURRENCY` or start fewer accounts at once. |
| "Model did not return valid JSON" | The chosen model is too weak for structured output. Use the default model. |
| Test Google Sheets: permission error | The sheet is not shared with the service account email as Editor. |
| Test Google Sheets: "needs at least 'account' and 'topic' columns" | Fix the header in row 1 of the first tab. |
| Sheet rows are not becoming accounts | Check Logs for "skipped" rows, and that the sheet sync time on the Dashboard is recent. |
| Cycle says "All upcoming slots already have content" | Normal: nothing new is needed until posts are published or rejected. |
| Post failed: "Missing twitter credentials" | Press Add keys and fill all four fields. |
| Post failed: X API 403 | The app is not set to Read and write, or the tokens were generated before changing it. Regenerate them. |
| Post failed: "Instagram posts need an image" | The Pinterest search found nothing. Edit the post, add an image URL, press Post now. |
| Posts marked "missed" | The agent was stopped or paused for over 12 hours past their time. Use Post now if you still want them. |
| "Could not decrypt a stored secret" | `MASTER_KEY` changed. Restore the old `.env`, or enter the keys again. |
| Research finds very few items | DuckDuckGo is rate limiting. It recovers by itself; fewer simultaneous accounts helps. |
| Port 8080 already in use | Change `PANEL_PORT` in `.env`, then `docker compose up -d`. |

---

## 18. Known limitations

- **Not yet tested with real keys**: the NVIDIA API, Google Sheets, and posting to X and Instagram ([section 1](#1-what-has-and-has-not-been-tested)).
- **Pinterest videos are not found.** Pinterest has no open search API, so it is searched through DuckDuckGo,
  which returns Pinterest images but not Pinterest videos. The `video_url` column stays empty unless you fill it by hand.
- **Videos are never posted.** Only images are published, even if a video URL is set.
- **Pinterest images belong to their owners.** Reposting them may infringe copyright; replace the image on a
  post if that matters for an account.
- **Reddit is not searched directly** (it blocks unauthenticated requests); viral posts come from web search.
- **Research depends on free search endpoints** (Google News RSS, DuckDuckGo) that can rate limit or change without notice.
- **Pause and stop are not instant.** They take effect at the agent's next step; an AI request already in progress finishes first.
- **One AI provider for all accounts**, and one admin user.
- **The schedule sheet is output only.** Edits made in the sheet are ignored and overwritten.
- **No engagement tracking.** The system does not read likes, replies or follower counts.
- **Platform rules still apply.** Automated posting must stay within X's and Instagram's automation policies and your API plan's limits.
