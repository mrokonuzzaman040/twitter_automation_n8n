# Social Agents

Automated research, content creation, scheduling and posting for many X/Twitter and Instagram accounts at once.
Everything runs in Docker and is controlled from a web admin panel. A local n8n instance runs alongside it and runs
the approval pipeline: Telegram notification, Approve buttons, and the decision back to the agents.

You give it a list of accounts and a topic for each. For every account it runs its own agent that:

1. researches the topic on the web (latest news, recent B2B offers, trending topics, viral posts, viral content)
   and on the social platform itself (top posts for the topic, and the recent posts of the target profiles you list),
2. writes posts from that research,
3. finds a Pinterest image for each post,
4. schedules the posts into that account's posting times and writes them to a Google Sheet,
5. sends every draft to you in Telegram with Approve buttons, and lists it on the Approvals page of the panel,
6. publishes a post **only after an admin approved it**. Anything not approved stays a draft and is never posted.

There is no automatic posting mode.

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
14. [n8n and Telegram approvals](#14-n8n-and-telegram-approvals)
15. [API reference](#15-api-reference)
16. [Project structure](#16-project-structure)
17. [Operations](#17-operations)
18. [Troubleshooting](#18-troubleshooting)
19. [Known limitations](#19-known-limitations)

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
| Target profiles: parsing, sheet column, form field | Tested, works |
| Target profile research through web search | Tested: real posts for X profiles; Instagram profiles return little or nothing |
| Target profile and top-post research through the X API and Instagram API | **Not tested** (needs your account credentials) |
| n8n container, automatic workflow import, events arriving in n8n | Tested, works |
| n8n calling the panel API with the API token | Tested, works |
| Approval rule: new posts are drafts, only approved posts reach the publisher | Tested, works |
| Approvals page: approve, approve + post now, back to draft, discard | API tested; page rendered with sample data, buttons not clicked in a browser |
| Telegram approval pipeline in n8n (draft message with buttons, approve / post now / keep as draft, presses from other chats ignored) | Tested against a **fake Telegram server**, works |
| Real Telegram bot | **Not tested** (no bot token was available) |

Use the two test buttons in Settings to check the NVIDIA and Google Sheets connections before starting agents,
before starting agents. Nothing is published without your approval, so you see every post before it goes out.

---

## 2. Requirements

- Docker with Docker Compose v2 (Docker Desktop on macOS/Windows, or Docker Engine on Linux).
- `openssl` on the host (only used once by `setup.sh`).
- An NVIDIA API key from https://build.nvidia.com (or a key for another supported provider).
- Optional: a Google Cloud service account for Google Sheets.
- Per account you want to post from: X developer app keys, or an Instagram Graph API token.

---

## 3. Install and run

### Prerequisites (All Operating Systems)

- Docker with Docker Compose v2 (Docker Desktop on macOS/Windows, or Docker Engine on Linux)
- `openssl` command-line tool (only used once by `setup.sh`)
- An NVIDIA API key from https://build.nvidia.com (or a key for another supported provider)
- Optional: a Google Cloud service account for Google Sheets
- Per account you want to post from: X developer app keys, or an Instagram Graph API token

### macOS

1. **Install Docker Desktop** (if not already installed):
   - Download from https://www.docker.com/products/docker-desktop/
   - Install and start Docker Desktop
   - Verify installation: `docker --version` and `docker compose version`

2. **Clone or download this repository** and navigate to it:
   ```sh
   cd /path/to/twitter_automation_n8n
   ```

3. **Run setup** (first time only):
   ```sh
   ./setup.sh
   ```
   This creates `.env` and prints the admin password. Save the `ADMIN_PASSWORD` value.

4. **Build and start the containers**:
   ```sh
   docker compose up -d --build
   ```

5. **Access the applications**:
   - Admin panel: http://localhost:8080
   - n8n: http://localhost:5678 (first time, create an owner account)

### Windows

1. **Install Docker Desktop** (if not already installed):
   - Download from https://www.docker.com/products/docker-desktop/
   - Install and start Docker Desktop
   - Verify installation in PowerShell: `docker --version` and `docker compose version`

2. **Clone or download this repository** and navigate to it:
   ```powershell
   cd C:\path\to\twitter_automation_n8n
   ```

3. **Run setup** (first time only):
   ```powershell
   bash setup.sh
   ```
   If `bash` is not available, you can use Git Bash or WSL. This creates `.env` and prints the admin password. Save the `ADMIN_PASSWORD` value.

4. **Build and start the containers**:
   ```powershell
   docker compose up -d --build
   ```

5. **Access the applications**:
   - Admin panel: http://localhost:8080
   - n8n: http://localhost:5678 (first time, create an owner account)

### Linux (Ubuntu/Debian)

1. **Install Docker and Docker Compose** (if not already installed):
   ```sh
   # Install Docker
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh

   # Add your user to the docker group (log out and back in after this)
   sudo usermod -aG docker $USER

   # Verify installation
   docker --version
   docker compose version
   ```

2. **Install OpenSSL** (if not already installed):
   ```sh
   sudo apt update
   sudo apt install openssl
   ```

3. **Clone or download this repository** and navigate to it:
   ```sh
   cd /path/to/twitter_automation_n8n
   ```

4. **Run setup** (first time only):
   ```sh
   ./setup.sh
   ```
   This creates `.env` and prints the admin password. Save the `ADMIN_PASSWORD` value.

5. **Build and start the containers**:
   ```sh
   docker compose up -d --build
   ```

6. **Access the applications**:
   - Admin panel: http://localhost:8080
   - n8n: http://localhost:5678 (first time, create an owner account)

### Linux (Fedora/CentOS/RHEL)

1. **Install Docker and Docker Compose** (if not already installed):
   ```sh
   # Install Docker
   sudo dnf -y install dnf-plugins-core
   sudo dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
   sudo dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

   # Start and enable Docker
   sudo systemctl start docker
   sudo systemctl enable docker

   # Add your user to the docker group (log out and back in after this)
   sudo usermod -aG docker $USER

   # Verify installation
   docker --version
   docker compose version
   ```

2. **Install OpenSSL** (if not already installed):
   ```sh
   sudo dnf install openssl
   ```

3. **Clone or download this repository** and navigate to it:
   ```sh
   cd /path/to/twitter_automation_n8n
   ```

4. **Run setup** (first time only):
   ```sh
   ./setup.sh
   ```
   This creates `.env` and prints the admin password. Save the `ADMIN_PASSWORD` value.

5. **Build and start the containers**:
   ```sh
   docker compose up -d --build
   ```

6. **Access the applications**:
   - Admin panel: http://localhost:8080
   - n8n: http://localhost:5678 (first time, create an owner account)

### Container Overview

Three containers start:

| Container | Image | Job |
|---|---|---|
| `web` | `social-agents` (built here) | Admin panel and JSON API on port 8080 |
| `worker` | `social-agents` (built here) | Master agent plus one agent per account |
| `n8n` | `n8nio/n8n:2.42.4` | Workflow automation on port 5678 ([section 14](#14-n8n-and-telegram-approvals)) |

`web` and `worker` mount the same Docker volume (`data`) at `/data`. The panel never talks to the worker directly: it writes
what you want (start, pause, stop) into the shared database and the worker obeys it within a few seconds.
Restarting `web` does not interrupt running agents.

### Common Commands

```sh
# View container logs
docker compose logs -f

# View logs for a specific service
docker compose logs -f web
docker compose logs -f worker
docker compose logs -f n8n

# Stop all containers
docker compose down

# Restart all containers
docker compose restart

# Rebuild after code changes
docker compose up -d --build

# Update environment variables after editing .env
docker compose up -d
```

---

## 4. Configuration file (.env)

Created by `setup.sh`. It is never copied into the Docker image and is ignored by git.

| Variable | Default | Meaning |
|---|---|---|
| `MASTER_KEY` | random 64 hex chars | Encrypts every stored API key and credential. Must be 16+ characters. **Back it up.** If it changes or is lost, saved secrets cannot be decrypted and must be entered again. |
| `ADMIN_PASSWORD` | random | Password for the admin panel. Change it here and restart `web`. |
| `API_TOKEN` | random | Lets n8n or your own scripts call the panel API with `Authorization: Bearer <token>`. Remove it to switch API-token access off. |
| `PANEL_PORT` | `8080` | Host port for the panel (bound to 127.0.0.1 only). |
| `N8N_PORT` | `5678` | Host port for n8n (bound to 127.0.0.1 only). |
| `TELEGRAM_BOT_TOKEN` | empty | Token of your Telegram bot from @BotFather. Empty means no Telegram messages are sent. |
| `TELEGRAM_CHAT_ID` | empty | The chat that receives drafts and is allowed to approve them. Button presses from any other chat are ignored. |
| `TZ` | `UTC` | Optional. Timezone n8n uses for its schedule triggers, e.g. `Asia/Dhaka`. |
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
4. **Target profiles** - in the account form (or the `target_profiles` sheet column) list the profiles the agent
   should study for that account.
5. **Credentials** - on each account row press **Add keys** and enter that account's posting credentials
   ([section 8](#8-posting-credentials)). Web research and content creation work without them. Publishing needs
   them, and so does reading the platform directly (top posts, target profiles with engagement numbers).
6. **Start** - press **Start** on an account, or **Start all**. The first cycle begins immediately.
7. **Telegram (recommended)** - put your bot token and chat id in `.env` ([section 14](#14-n8n-and-telegram-approvals))
   so drafts arrive in Telegram with Approve buttons.
8. **Approve** - press a button in Telegram, or open the **Approvals** page in the panel. Approved posts are
   published at their planned time; "post now" publishes within 30 seconds.

---

## 6. The admin panel

The navigation bar at the top switches between six pages. On the right it shows whether the master agent (the
`worker` container) is online, and the Sign out button. The Approvals item shows a counter with the number
of drafts waiting for approval.

### Dashboard

- **Stat cards**: accounts, agents running, drafts waiting for approval, approved, posted, failed (totals over all accounts).
- **All agents bar**:
  - **Start all / Pause all / Resume all / Stop all** apply the command to every account.
  - **Sync sheet now** makes the master agent read the master sheet on its next tick (within 3 seconds).
  - **Add account** opens the account form.
  - The text beside the title shows the time and result of the last sheet sync.
- **Agent table**, one row per account:
  - *Account*: handle, platform, where it came from (`panel` or `sheet`).
  - *Topic*: topic, posting times and timezone, and how many target profiles are set.
  - *Agent*: live status and the step it is on right now; the last error in red if the last cycle failed.
  - *Cycle*: when the last research-and-create cycle ran and when the next one is due.
  - *Posts*: counts of drafts, approved, posted and failed posts.
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
| Target profiles to research | empty | Profiles this account's agent studies on every cycle, up to 15. One per line or comma separated. Accepts `@handle`, a profile link (`https://x.com/name`, `https://instagram.com/name`), or `instagram:name` / `twitter:name`. A bare handle is taken as a profile on the account's own platform. |
| Own schedule sheet | empty | A separate schedule spreadsheet for this account; overrides the one in Settings. |

### Approvals

Every draft waiting for a decision, from all accounts, oldest planned time first. Each row shows the account,
the image and pin link, the text and hashtags, the research source and the planned time.

| Button | Effect |
|---|---|
| Approve | The post will be published at its planned time. If that time has already passed, it is published within 30 seconds. |
| Approve + post now | Asks for confirmation, then publishes within 30 seconds. |
| Edit | Change text, hashtags, image URL, video URL and planned time. The post stays a draft. |
| Discard | Throws the draft away. Its slot becomes free and is refilled on the next cycle. |
| Approve all | Approves every listed draft after a confirmation. |

A draft you do nothing with stays a draft forever and is never published.
Publishing is done by the account's agent, so an approved post only goes out while that agent is running
(not stopped or paused). The panel tells you when you approve a post for an account whose agent is not running.

### Content

Every post of one account, with a status filter. Same row layout as Approvals plus the status.

| Button | Shown for | Effect |
|---|---|---|
| Approve, Approve + post now, Discard | draft | Same as on the Approvals page. |
| Back to draft | approved, failed, missed, discarded | Withdraws the approval or revives the post as a draft. It will not be published until approved again. |
| Post now | failed, missed, discarded | Approves and publishes within 30 seconds. |
| Edit | everything not yet posted | Change text, hashtags, image URL, video URL and planned time. |

Every change here and on the Approvals page is also written to the schedule sheet and to Logs (agent `approval`).

### Research

Pick an account to see its latest cycle: the AI-written brief (a summary plus 8 to 12 content angles), the raw
findings grouped by category with links (the five web categories, plus "Top posts on the platform" and
"Target profiles" with likes and reposts), a "What works for target profiles" summary, and the last 20 cycles
with their result.

### Logs

The newest 200 events, for all accounts or one. Each event shows the time, account, which agent wrote it
(`master`, `agent`, `research`, `media`, `scheduler`, `publisher`, `approval`, `n8n`, `panel`) and the message. Warnings are
yellow, errors red. The log keeps the most recent 5,000 events.

### Settings

- **AI provider**: provider preset, API key, optional model and base URL overrides. "In use" shows the values
  that will actually be used.
- **Google Sheets**: service account key, master accounts sheet, content schedule sheet, sync interval in
  minutes (default 5), and whether accounts newly found in the sheet start automatically (default yes).
- **n8n**: the webhook URL events are sent to (default `http://n8n:5678/webhook/social-agents`), an on/off switch
  for events, a link to n8n, and whether the API token is set.
- **Save settings**, **Test AI provider**, **Test Google Sheets**, **Send test event to n8n**.

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
| `schedule_sheet` | schedule sheet, schedule_sheet_id | Own schedule spreadsheet for this account. |
| `target_profiles` | target profiles, targets, target accounts, competitors | Profiles to research, comma separated: `@handle`, profile links, or `instagram:name`. |

Example:

| account | platform | topic | target_profiles | tone | post_times | timezone |
|---|---|---|---|---|---|---|
| @aitools_daily | twitter | AI tools for small business | @OpenAI, @AnthropicAI, https://x.com/levelsio | witty | 09:00,13:00,18:00 | Asia/Dhaka |
| @saas_growth | instagram | B2B SaaS growth | hubspot, canva | expert | 10:00,16:00 | America/New_York |

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
   already have a draft, approved or posted post. At most 30. If there are none, the cycle ends without
   doing research.
2. **Research agent.** First the web: two searches for each of five categories, limited to the last 7 days:

   | Category | Sources |
   |---|---|
   | Latest news | Google News, DuckDuckGo News |
   | Recent B2B offers | Google News (partnership / deal / enterprise / launch), DuckDuckGo |
   | Trending topics | DuckDuckGo, Google News |
   | Viral posts | DuckDuckGo limited to x.com, reddit.com, linkedin.com; DuckDuckGo "most shared" |
   | Viral content | DuckDuckGo video search sorted by views, DuckDuckGo |

   Then the social platform itself:

   | Category | What is read | How |
   |---|---|---|
   | Top posts on the platform | X: the most relevant recent posts for the topic, ranked by likes + reposts + replies. Instagram: top posts of the topic's hashtag (first two meaningful words of the topic, e.g. `#aitools`). | The platform API with the account's own credentials. Skipped if the account has no credentials. |
   | Target profiles | The last 10 posts of every target profile with likes, reposts/comments and a link. | Platform API first; public web search of the profile if the API cannot be used. |

   When the platform API is used and when web search is used for a target profile:

   | Target is on | Account has complete credentials for that platform | Method |
   |---|---|---|
   | the account's own platform | yes | Platform API. If the API call fails, a warning is logged and web search is used. |
   | the account's own platform | no | Web search |
   | the other platform | (not applicable) | Web search |

   - **X API**: reading posts needs an X API plan that includes read access (the free plan is write-only).
   - **Instagram API**: uses Business Discovery, which only works for target profiles that are Business or Creator accounts.
   - **Web search** returns titles and snippets of the profile's recent posts without engagement numbers.

   All findings are saved. The AI then turns them into a brief: a summary, a "what works for target profiles"
   analysis (themes, hooks, formats, length), and 8 to 12 content angles. For the target profiles it is given the
   3 best posts of every profile, and it is told to learn from them, never to copy them. A source that fails is
   logged as a warning and skipped.
3. **Content agent.** The AI writes one post per free slot from the brief and the target-profile analysis, in the
   account's language and tone.
   It is given the last 20 posts so it does not repeat itself and is told not to invent facts.
   - X: body plus hashtags is forced to fit 280 characters (hashtags are dropped first, then the body is cut).
   - Instagram: a short multi-line caption with 6 to 10 hashtags.
4. **Media agent.** For each post it searches Pinterest for the post's visual phrase and saves the image link
   and the pin link. It never reuses an image the account has already used.
5. **Scheduler agent.** Assigns each post to a slot, saves it in the account database, and writes the rows to
   the schedule sheet. Every post is saved as a `draft`. It then sends a `drafts_ready` event to n8n, which
   forwards each draft to Telegram with Approve buttons.

Then the next cycle is set for `cycle hours` later. If a cycle fails, it is retried after 30 minutes and the
error is shown on the Dashboard.

### Publisher agent

It only ever looks at **approved** posts (status `scheduled`); drafts are invisible to it. Every 30 seconds, for
approved posts whose time has come:

- posts **one** post per run, so a backlog never goes out as a burst;
- a post more than 12 hours overdue (the agent was stopped or paused) is marked `missed` instead of being posted late;
- on success saves the link to the live post; on failure marks the post `failed` with the reason (it is not
  retried automatically, use **Post now**);
- updates the schedule sheet and sends a `post_published` or `post_failed` event to n8n.

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

**Post** (Approvals page, Content page and schedule sheet)

| Status | Meaning |
|---|---|
| draft | Written and given a planned time, waiting for approval. Never published in this state. |
| scheduled | Approved by an admin. Will be published at its planned time (shown as "approved" in the panel). |
| posted | Published; a link to the post is saved. |
| failed | Publishing was attempted and failed; the reason is shown. |
| missed | Its time passed by more than 12 hours while the agent was not running. |
| rejected | You discarded it (shown as "rejected"; can be brought back to draft). |

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

n8n keeps its own data (workflows, its credentials, execution history) in a separate volume,
`twitter_automation_n8n_n8n_data`.

---

## 12. Security

- **Encryption at rest.** The AI API key, the Google service account key and every account credential are
  encrypted (Fernet: AES-128-CBC with HMAC-SHA256) with a key derived from `MASTER_KEY`. Reading a database
  file without `.env` reveals no secrets.
- **Isolation.** Each account's credentials are only in that account's own database file.
- **Panel access.** One admin password, a signed session cookie valid for 7 days, `SameSite=Strict`.
  Failed logins are delayed by one second. Every API route requires the session.
- **API token.** `API_TOKEN` gives full API access without the password. It is passed to the n8n container so
  workflows can use it. Treat it like the password.
- **n8n.** Has its own login, created on first open. Credentials you add inside n8n (Telegram, Slack and so on)
  are stored by n8n in its own volume, encrypted with n8n's own key.
- **Network.** The panel and n8n ports are bound to `127.0.0.1` only, so they are not reachable from other machines.
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

## 14. n8n and Telegram approvals

A local n8n (version 2.42.4) runs in the same Docker stack at **http://localhost:5678**. The Python agents do
the research, writing and publishing. n8n runs the approval pipeline between them and you:

```
agent writes drafts ──► n8n ──► Telegram: one message per draft with buttons
                                   [✅ Approve] [🚀 Approve + post now] [📝 Keep as draft]
you press a button  ──► n8n ──► panel API ──► post is approved (or stays a draft)
agent publishes approved posts ──► n8n ──► Telegram: "published <link>" or "failed <reason>"
```

### Set up Telegram (5 minutes)

1. In Telegram open **@BotFather**, send `/newbot`, follow the two questions. Copy the token it gives you.
2. Open your new bot and press **Start** (a bot cannot message you before you do this).
3. Get your chat id: open **@userinfobot** and press Start; it replies with your numeric id.
   To use a group instead, add your bot to the group and use the group's id (a negative number).
4. Put both values in `.env`:
   ```
   TELEGRAM_BOT_TOKEN=123456789:AA...
   TELEGRAM_CHAT_ID=987654321
   ```
5. Apply: `docker compose up -d`
6. In the panel: Settings → **Send test event to n8n**. A message "Test event from the Social Agents panel"
   should arrive in Telegram.

Without these two values everything still works; you simply approve in the panel only.

### What you receive and what the buttons do

For every new draft:

```
📝 Draft for @aitools_daily (twitter)

<post text>

<hashtags>

🕒 Planned: Thu 08 Oct, 13:00
🖼 <image link>
[✅ Approve] [🚀 Approve + post now]
[📝 Keep as draft]
```

| Button | Result |
|---|---|
| ✅ Approve | The post is approved and will be published at its planned time. |
| 🚀 Approve + post now | The post is approved and published within 30 seconds. |
| 📝 Keep as draft | Nothing is published. The post stays a draft; you can still approve or edit it in the panel later. |
| (no button pressed) | Same as "Keep as draft": it stays a draft and is never published. |

After a press the buttons disappear and the bot replies under the draft with what happened (within about 10
seconds). If the account's agent is stopped or paused, the reply says so, because the post cannot go out until
the agent runs. You also get a message when a post is published (with its link), when publishing fails, and
when a research cycle fails.

Only presses coming from the chat in `TELEGRAM_CHAT_ID` are accepted. In a group, every member of that group can approve.

### The three workflows

They are imported automatically the first time the n8n container starts. Open http://localhost:5678 (it asks
you to create n8n's owner account once) to see or change them.

**1. "Social Agents - Events to Telegram"** (active)

```
Event from Social Agents (webhook) → Build message → Telegram set up? ─ no → nothing sent
                                                          │ yes
                                                   Are these new drafts? ─ yes → One item per draft → Telegram: draft with approve buttons
                                                          │ no
                                                   Telegram: notification
```

**2. "Social Agents - Telegram approvals"** (active)

```
Every 10 seconds → Telegram set up? → Telegram: get button presses → Read button presses
   ├─► From the admin chat? → Panel: apply the decision → Result text → remove the buttons → reply with the result → stop the button spinner
   └─► Telegram: mark presses as handled
```

It asks Telegram for new button presses every 10 seconds. This polling is used instead of a Telegram webhook
because a webhook needs a public HTTPS address and this n8n runs on localhost. Successful runs of this workflow
are not saved to n8n's execution history, so it does not fill up.

**3. "Social Agents - Daily summary and control"** (inactive example)

Reads `/api/overview` every morning at 08:00 and builds a one-line summary (accounts, agents running, drafts
waiting, failed posts). Add a notification node at the end and publish it to switch it on. It also contains an
unconnected "start all agents" request as an example of controlling agents from n8n.

### Events the agents send to n8n

| Event | Sent when | `data` |
|---|---|---|
| `drafts_ready` | A cycle finished and wrote drafts | `posts[]` with `id`, `text`, `hashtags`, `image_url`, `scheduled_at` (UTC), `scheduled_local` (account timezone, readable) |
| `post_published` | An approved post went live | `id`, `text`, `url` |
| `post_failed` | Publishing an approved post failed | `id`, `text`, `error` |
| `cycle_failed` | A research-and-create cycle failed | `run_id`, `error` |
| `test` | You pressed **Send test event to n8n** | `message` |

Envelope of every event:

```json
{
  "event": "drafts_ready",
  "time": "2026-10-08T03:00:00+00:00",
  "account": {"id": 1, "handle": "aitools_daily", "platform": "twitter", "topic": "...", "timezone": "Asia/Dhaka"},
  "data": { }
}
```

### Variables available inside n8n

| Variable | Value |
|---|---|
| `{{ $env.SOCIAL_AGENTS_URL }}` | `http://web:8080` (the panel, reachable from inside Docker) |
| `{{ $env.SOCIAL_AGENTS_TOKEN }}` | the `API_TOKEN` from `.env` |
| `{{ $env.TELEGRAM_BOT_TOKEN }}`, `{{ $env.TELEGRAM_CHAT_ID }}` | from `.env` |

With the header `Authorization: Bearer {{ $env.SOCIAL_AGENTS_TOKEN }}` a workflow can call every route in
[section 15](#15-api-reference). The Telegram calls are plain HTTP Request nodes, so no credential has to be
created inside n8n.

### Settings in the panel

Settings → n8n: the webhook URL events are sent to, an on/off switch, and **Send test event to n8n**. A failed
delivery is written to Logs as a warning and never stops an agent. With events switched off no Telegram
messages are sent; approval in the panel still works.

### Changing the shipped workflows

Edit them in n8n and publish. Your edits are kept across restarts. To go back to the shipped versions see
[section 17](#17-operations). To use a different channel (Slack, email, WhatsApp), replace the Telegram HTTP
nodes in workflow 1; approving through that channel needs your own version of workflow 2.

### Using an n8n you already run elsewhere

Remove the `n8n` service from `docker-compose.yml`, import the three files from `n8n/workflows/` into your n8n
and publish the first two. Set the webhook URL in Settings to your n8n's webhook address (from inside Docker,
your Mac is `http://host.docker.internal:5678`). In your n8n set the environment variables `SOCIAL_AGENTS_URL=http://localhost:8080`,
`SOCIAL_AGENTS_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` and `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`.

---

## 15. API reference

The panel is a client of this JSON API, so anything the panel does can be scripted. All routes except login
need the session cookie or the header `Authorization: Bearer <API_TOKEN>`. Errors return `{"detail": "message"}`.

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
| PATCH | `/api/accounts/{id}/posts/{post_id}` | any of `text`, `hashtags`, `image_url`, `video_url`, `scheduled_at`, `action` | Edit or act on a post. Actions: `approve` (publish at planned time), `post_now` (approve and publish now), `draft` (back to draft), `reject` (discard). Returns `status`, `scheduled_at`, `agent_running`. |
| GET | `/api/drafts` | | Every draft waiting for approval, all accounts |
| GET | `/api/accounts/{id}/research` | | Latest brief, its findings, last 20 cycles |
| GET | `/api/events?account_id=&limit=` | | Activity log |
| GET | `/api/settings` | | Current settings (no secrets) |
| PUT | `/api/settings` | setting fields | Save settings |
| POST | `/api/settings/test-llm` | | Test the AI provider |
| POST | `/api/settings/test-sheets` | | Test reading the master sheet |
| POST | `/api/settings/test-n8n` | | Send a test event to n8n |

Example:

```sh
curl -c cookies.txt -X POST localhost:8080/api/login -H 'Content-Type: application/json' -d '{"password":"..."}'
curl -b cookies.txt -X POST localhost:8080/api/accounts/1/action -H 'Content-Type: application/json' -d '{"action":"pause"}'

# or with the API token, no login needed
curl -H "Authorization: Bearer $API_TOKEN" localhost:8080/api/overview
```

Account fields: `platform`, `handle`, `topic`, `tone`, `language`, `post_times`, `timezone`, `cycle_hours`,
`schedule_sheet_id`, `target_profiles`.

---

## 16. Project structure

```
docker-compose.yml     the three services (web, worker, n8n) and their volumes
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
  research.py          research agent: web sources and brief
  social.py            research agent: platform top posts and target profiles (X API, Instagram API, web fallback)
  hooks.py             events sent to n8n
  content.py           content agent: post writing and length rules
  media.py             media agent: Pinterest search
  scheduler.py         scheduler agent: posting slots and saving the schedule
  publisher.py         publisher agent: X and Instagram posting
  sheets.py            Google Sheets reading and writing
  web.py               admin panel API
  static/index.html    admin panel UI (single file)
n8n/
  start.sh             imports the workflows on first start, then starts n8n
  workflows/events.json    "Social Agents - Events to Telegram"
  workflows/approvals.json "Social Agents - Telegram approvals"
  workflows/control.json   "Social Agents - Daily summary and control"
```

---

## 17. Operations

```sh
docker compose ps                       # are all three containers running?
docker compose logs -f worker           # live agent activity
docker compose logs -f web              # panel requests and errors
docker compose logs -f n8n              # n8n
docker compose restart worker           # restart all agents (they resume by themselves)
docker compose down                     # stop everything, data is kept
docker compose up -d --build            # start again / apply code changes
```

**Backup** (databases plus the key that decrypts them):

```sh
docker run --rm -v twitter_automation_n8n_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/social-agents-data.tgz -C /data .
docker run --rm -v twitter_automation_n8n_n8n_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/n8n-data.tgz -C /data .
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

**Re-import the shipped n8n workflows** (overwrites your edits to those three workflows):
`docker compose exec n8n rm /home/node/.n8n/.social-agents-workflows-v2 && docker compose restart n8n`.

**Erase everything** (all accounts, posts, saved credentials and all n8n data, cannot be undone): `docker compose down -v`.

---

## 18. Troubleshooting

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
| Cycle says "All upcoming slots already have content" | Normal: every upcoming slot already has a draft or an approved post. |
| Post failed: "Missing twitter credentials" | Press Add keys and fill all four fields. |
| Post failed: X API 403 | The app is not set to Read and write, or the tokens were generated before changing it. Regenerate them. |
| Post failed: "Instagram posts need an image" | The Pinterest search found nothing. Edit the post, add an image URL, press Post now. |
| Posts marked "missed" | The agent was stopped or paused for over 12 hours past their time. Use Post now if you still want them. |
| "Could not decrypt a stored secret" | `MASTER_KEY` changed. Restore the old `.env`, or enter the keys again. |
| Research finds very few items | DuckDuckGo is rate limiting. It recovers by itself; fewer simultaneous accounts helps. |
| Log: "API could not read @name ... using web search instead" | The platform API refused. On X this usually means the API plan has no read access; on Instagram the target is not a Business/Creator account. Research continues with web search. |
| Target profiles section is empty on the Research page | No target profiles are set on the account, or web search returned nothing for them this cycle. |
| Log: "Event ... not delivered: n8n answered 404" | The "Social Agents - Events to Telegram" workflow is not published in n8n. Open it in n8n and publish it. |
| No Telegram messages arrive | Check `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env` and run `docker compose up -d`. You must have pressed Start in your bot. Press **Send test event to n8n**, then open the latest execution of "Social Agents - Events to Telegram" in n8n (Executions): the output of the Telegram node shows Telegram's answer, including its error text. |
| Pressing a Telegram button does nothing | Wait 10 seconds (presses are collected every 10 seconds). Check that "Social Agents - Telegram approvals" is published in n8n, and that you press from the chat whose id is in `TELEGRAM_CHAT_ID`. |
| Approved post is not published | The account's agent is stopped or paused; start it. Approved posts more than 12 hours past their time become "missed". |
| Log: "Event ... not delivered: n8n not reachable" | The n8n container is down (`docker compose ps`), or the webhook URL in Settings is wrong. Turn events off in Settings if you do not use n8n. |
| n8n workflow fails with an access error on `$env` | `N8N_BLOCK_ENV_ACCESS_IN_NODE` must be `false` (it is in `docker-compose.yml`). |
| Port 5678 already in use | Change `N8N_PORT` in `.env`, then `docker compose up -d`. |
| Port 8080 already in use | Change `PANEL_PORT` in `.env`, then `docker compose up -d`. |

---

## 19. Known limitations

- **Platform research depends on what the platforms allow.** With the X API it needs a paid plan with read
  access. With the Instagram API it only reads Business/Creator profiles and one hashtag per cycle (Instagram
  allows 30 different hashtags per week). Without API access the agent falls back to web search, which gives
  post text for X profiles but little or nothing for Instagram profiles, and no engagement numbers.
- **The agents do not log in to X or Instagram as a browser** and do not scrape them directly.
- **n8n runs the approval pipeline, not the whole engine.** Research, writing, scheduling and the actual posting
  run in the Python agents. n8n carries drafts to Telegram and decisions back.
- **Telegram was tested with a simulated Telegram server only**, not with a real bot.
- **Telegram button presses take up to about 10 seconds** to be processed, and drafts are sent as text with an
  image link, not as an attached photo.
- **Discarding is only possible in the panel.** In Telegram the choices are approve, approve + post now, keep as draft.
- **Not yet tested with real keys**: the NVIDIA API, Google Sheets, platform API research, and posting to X and Instagram ([section 1](#1-what-has-and-has-not-been-tested)).
- **Pinterest videos are not found.** Pinterest has no open search API, so it is searched through DuckDuckGo,
  which returns Pinterest images but not Pinterest videos. The `video_url` column stays empty unless you fill it by hand.
- **Videos are never posted.** Only images are published, even if a video URL is set.
- **Pinterest images belong to their owners.** Reposting them may infringe copyright; replace the image on a
  post if that matters for an account.
- **Reddit is not searched directly** (it blocks unauthenticated requests); viral posts come from web search.
- **Research depends on free search endpoints** (Google News RSS, DuckDuckGo) that can rate limit or change without notice.
- **Approved posts are published by the account's agent**, so they wait while that agent is stopped or paused.
- **Pause and stop are not instant.** They take effect at the agent's next step; an AI request already in progress finishes first.
- **One AI provider for all accounts**, and one admin user.
- **The schedule sheet is output only.** Edits made in the sheet are ignored and overwritten.
- **No engagement tracking.** The system does not read likes, replies or follower counts.
- **Platform rules still apply.** Automated posting must stay within X's and Instagram's automation policies and your API plan's limits.
