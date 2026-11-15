# GenAI Fund outreach on X

A tool for finding AI and robotics builders on X and starting warm, personal conversations with them from your own account.

- **AI does the reading and writing.** It finds people from a topic or from accounts you already rate, explains why each one fits using quotes from their own posts, and drafts a short personal DM.
- **A person approves every message.** Nothing is sent until you approve the exact text.
- **The app sends and tracks.** Approved messages go out at a safe pace, nobody is ever messaged twice, and replies show up under "Needs attention".

**Status:** verified end to end on real X and OpenAI on 15 Nov 2026: connect account, search, AI fit judging, AI draft, approve, automatic send, reply, sync. The test used two accounts controlled by the author. Not yet run on real X: sending to people outside the test list (the "operator-approved" rule below). Details are in [docs/VERIFICATION.md](docs/VERIFICATION.md).

---

## Contents

1. [What it does](#1-what-it-does)
2. [What you need](#2-what-you-need)
3. [Set up (about 5 minutes)](#3-set-up-about-5-minutes)
4. [Try it on synthetic data first](#4-try-it-on-synthetic-data-first)
5. [Connect your own X account and AI key](#5-connect-your-own-x-account-and-ai-key)
6. [Send one safe test message](#6-send-one-safe-test-message)
7. [Switch from testing to real outreach](#7-switch-from-testing-to-real-outreach)
8. [Using it day to day](#8-using-it-day-to-day)
9. [How it never double-messages](#9-how-it-never-double-messages)
10. [Blocked actions and what to do](#10-blocked-actions-and-what-to-do)
11. [Limitations](#11-limitations)
12. [X rules this tool follows](#12-x-rules-this-tool-follows)
13. [Costs](#13-costs)
14. [How it works](#14-how-it-works)
15. [All settings](#15-all-settings)
16. [Tests](#16-tests)
17. [Troubleshooting](#17-troubleshooting)
18. [Documents](#18-documents)

---

## 1. What it does

How each part of the brief is covered:

| The brief asks for | How the tool does it | Where |
|---|---|---|
| Start from a target segment **or seed accounts** | Type topics, or enter 1 to 3 X handles you already rate. For seeds, the AI reads their recent posts and searches for people doing similar work. | Discover |
| Find people and **explain why they fit** | One X search, a keyword score, then the AI judges the top 10: strong, possible or weak, with a reason and the quotes it rests on. Every quote is checked word for word against the person's posts. | Discover |
| Draft **personalised** DMs from **real evidence** | "Draft for top matches" writes a short message per person that mentions something they actually posted. Drafts with made-up quotes, links, missing opt-out lines or over 500 characters are rejected. | Review |
| Drafts **for us to review and approve** | Each draft is a card: reason, quotes, source posts, editable text. Approve, edit, rewrite with a note, skip, or mark do-not-contact. | Review |
| Send from **our connected account** within X's rules and limits | Your own account via X's official OAuth. Approved messages go out one at a time, 2 minutes apart, at most 10 a day (both adjustable). | Activity |
| **Never double-messages** anyone | One record per person, a check of past DMs before sending, no automatic retries, and a stored key per message so a crash or restart cannot resend. See [section 9](#9-how-it-never-double-messages). | Built in |
| Show **what was sent, who replied, what needs attention** | Activity lists every message with its status, its place in the queue and replies. "Needs attention" shows new replies and problems. Replies are checked automatically or with "Sync all now". | Activity |
| Usable **without the author** | This README, clear on-screen reasons for every hold or block, and a synthetic mode to practise in. | |
| **Limitations and blocked actions clear** | Every blocked action shows its reason in plain words. See [section 10](#10-blocked-actions-and-what-to-do) and [section 11](#11-limitations). | |

![Review page: reason, quotes and the editable draft](docs/screenshots/review.png)

![Discover page with AI fit](docs/screenshots/discover-ai.png)

---

## 2. What you need

**To try it on synthetic data:** only Git and Docker Desktop. No Python, accounts, keys or cost.

**To use it on real X:**

| Need | Details |
|---|---|
| X developer account with credits | Pay-per-use credits on the X Developer Console. About USD 5 covers testing and a demo comfortably (see [Costs](#13-costs)). |
| An X app with user sign-in | Set up in [section 5](#5-connect-your-own-x-account-and-ai-key). Permissions "Read and write and Direct message". |
| The X account messages are sent from | You connect it inside the app. It stays yours; the app stores its token encrypted. |
| For testing: a second X account you control | Real test messages may only go to accounts you control or people who agreed. |
| An AI key (recommended) | OpenAI (default models `gpt-6-luna`, backup `gpt-6.1-terra`) or Google Gemini. Without one the app still works, with keyword ranking and a fill-in template instead of AI drafts. |
| Software | Git and Docker Desktop. Or, without Docker: Python 3.12 and PostgreSQL 16 or newer (tested on 18). |

**Nothing from the author's setup is included.** No password, keys, accounts or data are in this repository. You create your own as you go.

---

## 3. Set up (about 5 minutes)

### Option A: Docker (recommended)

Three commands. Docker Desktop must be running. The app image is published on Docker Hub as [archit690/genai-outreach](https://hub.docker.com/r/archit690/genai-outreach) for Intel/AMD and Apple silicon, so nothing is built on your computer. Tested on 15 Nov 2026 from a clean folder: the image downloaded, setup and start each took about 5 seconds after that.

1. **Get the code**
   ```
   git clone https://github.com/ArChIt690/genai-outreach
   cd genai-outreach
   ```
2. **Choose your password** (the first run also downloads the app image, about 140 MB)
   ```
   docker compose run --rm setup
   ```
   It asks you to choose an operator password (at least 12 characters, typed twice; nothing is shown as you type) and writes a `.env` file in this folder with a fresh encryption key. Your password is stored only as a hash. `.env` is ignored by git; never commit it. The command refuses to overwrite an existing `.env`.
3. **Start**
   ```
   docker compose up
   ```
   This starts PostgreSQL and the app and sets up the database. Wait for "Application startup complete".
4. **Open** http://127.0.0.1:8000 and sign in with your password.

To stop: `Ctrl+C`, or `docker compose down`. To start again later: `docker compose up`. To get the newest published image: `docker compose pull`, then `docker compose up`. To run your own local changes instead of the published image: `docker compose up --build`.

To change your password later: `docker compose run --rm setup python -m scripts.bootstrap --reset-password`, then restart.

On Linux, if `.env` can't be written, run the setup as yourself: `docker compose run --rm --user "$(id -u):$(id -g)" setup`.

If port 8000 is busy on your computer, change `"127.0.0.1:8000:8000"` in `compose.yaml` to another port, for example `"127.0.0.1:8080:8000"`, and set `APP_ORIGIN=http://127.0.0.1:8080` and `X_CALLBACK_URL=http://127.0.0.1:8080/oauth/x/callback` in `.env`.

**For the maintainer: publishing a new image** after code changes (needs `docker login` as the image owner):
```
docker buildx build --platform linux/amd64,linux/arm64 -t archit690/genai-outreach:latest --push .
```
Build from a clean checkout of committed code, so untracked local files never end up in the image.

### Option B: without Docker

Use this if you already run PostgreSQL. This is the path the author used during development and the live test.

1. Get the code (step 1 above), then install the Python packages:
   ```
   python -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements.lock
   ```
   `python` must be 3.12 or newer (on Windows, `py -3.12 -m venv .venv` picks it if several are installed). On macOS or Linux, use `.venv/bin/python` instead of `.venv\Scripts\python.exe` in every command. Tested: about 80 seconds.
2. Create an empty database:
   ```
   createdb -U <your postgres user> outreach
   ```
3. Create your settings and password, pointing at that database:
   ```
   .venv\Scripts\python.exe -m scripts.bootstrap --fixture-demo --database-url "postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/outreach"
   ```
4. Set up the tables and start:
   ```
   .venv\Scripts\python.exe -m alembic upgrade head
   .venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
   ```
5. Open http://127.0.0.1:8000 and sign in.

Keep `--no-access-log`: it stops X sign-in codes from being written to logs. Run exactly one app process; the send queue runs inside it.

To change your password later: `.venv\Scripts\python.exe -m scripts.bootstrap --reset-password`, then restart.

---

## 4. Try it on synthetic data first

Setup starts in **fixture mode**: five made-up people, made-up posts, a pretend X. Nothing reaches X. Every page shows a yellow "Synthetic workspace" banner.

To see the AI working, add an AI key first (one line in `.env`, see [section 5, step 3](#5-connect-your-own-x-account-and-ai-key)), then restart. Only the made-up posts are sent to the AI. Without a key, steps 1 to 3 still work with keyword ranking and template drafts.

To let the made-up people be "messaged", set this in `.env` and restart:
```
OUTREACH_POLICY=operator_approved
```

Then:

1. **Settings:** under "Who is writing, and why?", fill in a sender name and purpose, tick "I understand that X history is limited to 30 days", and save. **The send queue waits until this box is ticked.**
2. **Discover:** search `robotics, embodied AI`. Each person shows a fit, a reason and quotes. Try "Or start from accounts you already rate" with `@ada_robotics` too.
3. Click **Draft for top matches**. You land on **Review**.
4. On a card: read the reason and quotes, edit the text or type a note and click **Rewrite**, then **Approve and queue**.
5. **Activity:** watch the status change to **sent** (within 30 seconds; later messages wait 2 minutes each).
6. Open the person's page, type a reply under "Synthetic recipient reply", click **Add fixture reply**, then **Sync all now** in Activity. The row moves to **Needs attention**.

Fixture and live data must use separate databases (the app refuses to start on a mix). Section 5 shows how to switch.

---

## 5. Connect your own X account and AI key

### Step 1: create the X app (about 10 minutes, on X's site)

In the [X Developer Console](https://developer.x.com), open your app and:

1. **Settings → User authentication settings → Set up** (or Edit):
   | Field | Value |
   |---|---|
   | App permissions | **Read and write and Direct message** |
   | Type of App | **Web App, Automated App or Bot** (confidential client) |
   | Callback URI / Redirect URL | `http://127.0.0.1:8000/oauth/x/callback` |
   | Website URL | any URL of yours |
2. Save. Without "Direct message" permission the app can read but not send.
3. **Keys and tokens → OAuth 2.0 Keys:** copy the **Client ID** and **Client Secret**. You don't need the Bearer Token, Consumer Key or Access Token.
4. Make sure the app's project has credits (Billing → Credits).

### Step 2: switch the app to live mode

Live data needs its own empty database.

- **Docker:** run `docker compose down -v` (this deletes the synthetic data), then continue.
- **Without Docker:** create a second database, e.g. `createdb -U <user> outreach_live`, and point `DATABASE_URL` at it in step 3.

### Step 3: edit `.env`

Change these lines (edit the existing ones; don't add duplicates):

```
APP_MODE=live
X_CLIENT_ID=your-client-id
X_CLIENT_SECRET=your-client-secret
DRAFT_PROVIDER=openai
OPENAI_API_KEY=your-openai-key
OUTREACH_POLICY=test_allowlist
AUTO_SYNC_MINUTES=0
```

- For Gemini instead: `DRAFT_PROVIDER=gemini` and `GEMINI_API_KEY=...`.
- Without Docker, also: `DATABASE_URL=postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/outreach_live`
- `AUTO_SYNC_MINUTES=0` stops background reply checks (they cost money) while testing. You can use "Sync all now" instead.

**Important (without Docker):** if `OPENAI_API_KEY` or `GEMINI_API_KEY` is also set in your operating system's environment variables, that value wins over `.env`. Remove it or make it match, then restart from a new terminal. (This caused the only failure in the author's live test.)

Restart the app. The top bar should now say **Live mode**.

### Step 4: connect and set up

1. **Settings → Connect with X.** Sign in to X as the account messages should come **from**, and approve. Settings then shows that account as Authorized.
2. **Settings → "Who is writing, and why?"**:
   - **Sender name:** how messages should introduce you, e.g. "Archit from GenAI Fund".
   - **Purpose:** one true line about why you are reaching out. The AI uses only this to explain who is writing and why; the personal part comes from each person's own posts.
   - Tick the **30-day history** box, then save.

Changing the sender name or purpose later cancels earlier approvals and test consent. That is deliberate.

---

## 6. Send one safe test message

Do this once before any real outreach. It runs the whole real path while making it impossible to message anyone else. It costs about USD 0.10 to 0.20 of X and under one cent of AI.

1. **Pick the test recipient:** a second X account you control. Have the two accounts follow each other.
2. **Find its numeric X ID** (the number, not the @handle), with any X user-ID lookup tool. Put it in `.env` and restart:
   ```
   TEST_RECIPIENT_IDS=1234567890123456789
   ```
3. **Settings → Register a test recipient:** enter the handle, a short consent note such as "My own second account", tick "I control this recipient account", then **Record test consent**.
4. **From the second account, post something with a rare phrase** and a first-person line, for example:
   > I'm testing a tidewater gripper on low-cost robot arms this week.

   "I'm testing" (or building, researching, developing) earns enough evidence for the app to draft.
5. **Discover:** search the rare phrase, e.g. `tidewater gripper`. The second account should appear with an AI fit, reason and quote. A brand-new post can take 10 to 15 minutes to become searchable.
6. **Draft for top matches → Review.** Read the draft. Edit or Rewrite if you like.
7. **Approve and queue.** Within about 30 seconds Activity shows **sent**.
8. **On the second account, open Chat → Requests.** The message is there (it lands in Requests if that account didn't follow the sender when it was sent). Reply to it.
9. **Activity → Sync all now.** The row moves to **Needs attention**. The test is complete.

---

## 7. Switch from testing to real outreach

Only do this once your organisation has decided to run this outreach from its own account, and after section 6 worked.

1. In `.env`:
   ```
   OUTREACH_POLICY=operator_approved
   ```
2. Optionally adjust the pace:
   ```
   DAILY_SEND_LIMIT=10
   SEND_MIN_GAP_SECONDS=120
   AUTO_SYNC_MINUTES=180
   ```
   Reply checks cost about USD 0.01 per conversation per check; 180 minutes is about USD 1.12 per conversation over 14 days. 720 is a cheaper choice, 0 turns them off.
3. Restart. The top bar and Settings now say **Operator-approved sending**.

What changes: any person the app discovers can be messaged once you approve the exact text. The test list and recorded consent are no longer required for evidence-based messages.

What stays enforced: a person approves every message; nobody gets a second first message; the do-not-contact list; STOP replies; the pause button; the daily limit, pacing and budget caps; a fresh re-read of the quoted posts before sending.

To go back, set `OUTREACH_POLICY=test_allowlist` and restart. Queued messages to people not on the test list are taken out of the queue with a note; none are sent.

---

## 8. Using it day to day

1. **Discover:** search by topics (one to five, comma separated), or start from one to three seed accounts. Results are ordered strong, possible, unjudged, weak. Each card shows the AI's reason, the quotes behind it and the keyword points.
2. **Draft for top matches:** drafts for every strong or possible person, up to 10, skipping anyone already contacted, blocked or drafted. Nothing is sent.
3. **Review**, for each card:
   - **Approve and queue:** approves exactly the text in the box, including any edit you just made.
   - **Save edit:** keeps your changes without approving.
   - **Rewrite:** the stronger model writes a new draft from the same posts. Add a note such as "shorter" or "ask about the benchmark".
   - **Skip:** hides the draft without blocking the person.
   - **Do not contact:** blocks the person permanently.
4. **Activity:** every message, its status, its place in the queue, any hold reason and replies. **Needs attention** shows new replies, refused messages and anything uncertain. **Sync all now** checks replies immediately.
5. **Person page:** the evidence, the full conversation, send history, and a manual "Mark replies handled".
6. **Settings:** pause or resume sending, the active send rule and limits, X spend estimate, the **AI usage** panel (every AI call with model, tokens, time and result), and a purge of stored post and reply text.

A reply of "STOP" adds the person to the do-not-contact list automatically.

---

## 9. How it never double-messages

- **One record per person.** The database allows only one outreach record per sender and recipient.
- **Past DMs are checked before sending.** If X shows any earlier message from you to that person, the send is blocked.
- **No automatic retries.** If X's answer is unclear, the message is marked "unknown", the sender is held, and the queue stops until a person checks it ("Check uncertain outcome" on the person's page).
- **A stored key per message.** It is saved when you approve, before anything is sent. After a crash or restart, the app finds the stored result instead of sending again.
- **Database locks.** Two sends of the same message at the same moment cannot both go through.

---

## 10. Blocked actions and what to do

Every block shows its reason on screen. The ones you are most likely to meet:

| You see | Why | What to do |
|---|---|---|
| Queue **holding: history acknowledgement required** | The 30-day history box isn't ticked | Settings → tick it → Save |
| Queue **holding: pacing** | Less than `SEND_MIN_GAP_SECONDS` since the last send | Wait; it continues by itself |
| Queue **holding: daily limit** | `DAILY_SEND_LIMIT` reached (UTC day) | Wait for the next UTC day, or raise the limit |
| Queue **holding: rate limited** | X asked to slow down | Wait; the app retries after X's time (or 15 minutes) and keeps your approval |
| Queue **holding: sending paused / sending disabled** | Pause button, or `SEND_ENABLED=false` | Settings → Resume, or set `SEND_ENABLED=true` and restart |
| Queue **holding: sender busy** | A previous send has an unknown outcome | Open that person → Check uncertain outcome, or Freeze this contact |
| **recipient not allowed** | Test-list rule is on and the person isn't on `TEST_RECIPIENT_IDS` | Expected while testing; see section 7 |
| **consent required** | Test-list rule: no valid consent (or the purpose changed) | Settings → Register a test recipient again |
| **do not contact** | You blocked them, or they replied STOP | None; this is permanent |
| **already contacted** | You messaged them before (here or directly on X) | None; continue in X |
| **approval stale** | The text changed in another tab | Refresh and approve again |
| **budget exceeded** | `X_BUDGET_USD` reached by the app's own estimate | Check X billing, then raise the cap |
| Message **rejected: X permission or recipient restricted** | The person only accepts DMs from people they follow, or the app lacks DM permission | Nothing to fix for that person; check app permissions if it happens to everyone |
| "**AI fit judging was unavailable**" / draft labelled **fallback** | The AI call failed, or its answer failed the checks | Settings → AI usage shows the error code. The app continues with keyword ranking or the template |

---

## 11. Limitations

- **Cold DMs usually land in Requests**, where many people don't look. People who accept DMs only from accounts they follow cannot be reached; X refuses and the app marks it rejected. The app does not follow anyone to get around this.
- **Search covers X's last seven days** only. Seed accounts must have posted in that window.
- **DM history covers 30 days**, so the duplicate check cannot see older messages sent outside this app.
- **Seed accounts find similar people,** not the seed's followers or contacts.
- **The AI judges only the top 10** keyword matches per search.
- **Quote checks prove the quotes are real,** not that the AI's summary is fair. You still read each draft.
- **One operator and one sending account.** Run one app process.
- **The daily limit and gap are our caution,** not verified X quotas.
- **Not yet run on real X:** operator-approved sending to people outside the test list, and the Rewrite model (`gpt-6.1-terra`) against the real API.

Full list: [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md).

---

## 12. X rules this tool follows

- Official X API only: no scraping, no browser automation, no bypassing restrictions.
- A person approves every message. No message is sent automatically without approval.
- One message at a time, with a minimum gap and a daily cap. X's rate limits and reset times are respected.
- No automatic follows, likes, retries or follow-up messages.
- Every message ends with an opt-out line; a STOP reply blocks further contact automatically.
- Only public profile text and public posts go to the AI. Private DMs and tokens never do.
- Tokens are stored encrypted; secrets live only in `.env`, which git ignores.

---

## 13. Costs

**Paid tools:** the X API (pay per use) and the OpenAI API (or Gemini). No hosting is needed; it runs on your computer.

| Action | Expected cost |
|---|---|
| One search (up to 50 posts, 20 people) | about USD 0.45 at most; a narrow search costs cents |
| One seed account | about USD 0.06, plus the search |
| One approved message (re-read posts, check past DMs, send) | about USD 0.05 |
| Reply checks | about USD 0.01 per conversation per check |
| AI: one search judged plus ten drafts (gpt-6-luna) | about USD 0.001 to 0.01 |
| AI: one Rewrite (gpt-6.1-terra) | about USD 0.001 to 0.01 |
| **The author's full live test** | **about USD 0.18 of X, under 1 cent of AI** |

Example day at the defaults: one search and ten messages cost about USD 1 of X, plus up to about USD 11 of reply checks spread over the next 14 days (set `AUTO_SYNC_MINUTES` higher or to 0 to cut this).

Caps you control: `X_BUDGET_USD` (default 5; the app stops X calls when its estimate reaches it), `AI_DAILY_CALL_LIMIT` (default 200 AI calls a day), `DAILY_SEND_LIMIT`. Prices are from X's and OpenAI's pages in November 2026; check current prices before running. Details: [docs/COSTS.md](docs/COSTS.md).

---

## 14. How it works

One Python web app (FastAPI) and one PostgreSQL database. All AI calls go through one module that tries a backup model when the first is busy, caps daily calls and logs every call. A background thread inside the app sends approved messages at the set pace and checks for replies. The existing send function re-checks every rule immediately before each send.

Diagrams of the components, the full flow, the sending sequence and the data model: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## 15. All settings

Set in `.env`; restart the app after any change.

| Setting | Default | Meaning |
|---|---|---|
| `APP_MODE` | fixture | `fixture` (synthetic) or `live` (real X). Each needs its own database. |
| `DATABASE_URL` | local | PostgreSQL connection. Docker sets this for you. |
| `APP_ORIGIN` / `X_CALLBACK_URL` | 127.0.0.1:8000 | Must match the address in your browser and in the X app. |
| `X_CLIENT_ID` / `X_CLIENT_SECRET` | empty | From your X app's OAuth 2.0 keys. |
| `SEND_ENABLED` | false (setup with `--fixture-demo` sets true) | Master switch for sending. |
| `OUTREACH_POLICY` | test_allowlist | Who can be messaged; see section 7. |
| `TEST_RECIPIENT_IDS` | empty | Numeric X IDs allowed under the test-list rule, comma separated. |
| `DRAFT_PROVIDER` | template | `openai`, `gemini`, `anthropic` (untested) or `template` (no AI). |
| `OPENAI_API_KEY` | empty | Your OpenAI key. |
| `OPENAI_MODEL` / `OPENAI_STRONG_MODEL` | gpt-6-luna / gpt-6.1-terra | Everyday model; backup and Rewrite model. |
| `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_FALLBACK_MODEL` | empty, gemini-2.5-flash, gemini-flash-lite-latest | For Gemini. |
| `AI_DAILY_CALL_LIMIT` | 200 | AI calls per UTC day. |
| `DRAFT_LIMIT_PER_SESSION` | 40 | Drafts per sign-in. |
| `DAILY_SEND_LIMIT` | 10 | Send attempts per UTC day. |
| `SEND_MIN_GAP_SECONDS` | 120 | Minimum time between queued sends. |
| `QUEUE_TICK_SECONDS` | 30 | How often the background worker wakes. |
| `AUTO_SYNC_MINUTES` | 180 | Minutes between automatic reply checks, for 14 days after a send. 0 = off. |
| `WORKER_ENABLED` | true | Set false to stop automatic sending and reply checks. |
| `X_BUDGET_USD` | 5 | Cap on the app's estimate of X spend. |
| `HISTORY_LIMIT_ACKNOWLEDGED` | false | Same as ticking the 30-day history box in Settings. |

Sender name, purpose, the history tick, the connected account and test consent are set in the app's Settings page and stored in the database.

---

## 16. Tests

251 automated tests, including real-database concurrency tests and two browser tests. Running them needs the Python setup from Option B and a PostgreSQL database. They use synthetic data and fake AI and X servers; they never call real services and strip real keys from their environment.

```
$env:TEST_DATABASE_URL="postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/outreach_test"
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check .
```

The test database name must start with `outreach_test`; its tables are emptied on every run. Browser tests use Microsoft Edge on Windows, or set `BROWSER_EXECUTABLE`; skip them with `-m "not browser"`.

---

## 17. Troubleshooting

| Problem | Fix |
|---|---|
| No "Connect with X" button | `APP_MODE` is still `fixture`. Set `live` (with a live database) and restart. |
| `MODE_MISMATCH` on start | The database was used in the other mode. Use a separate database (Docker: `docker compose down -v`). |
| AI calls fail with `HTTP_401` | The AI provider refused the key. A key set in your operating system's environment overrides `.env`; remove it or make it match, and restart from a new terminal. |
| Sent DM not visible to the recipient | X shows DMs under Chat. Messages from accounts the recipient doesn't follow arrive under Requests. |
| New post not found by search | X can take 10 to 15 minutes to make a new post searchable. |
| "Insufficient professional evidence" when drafting | The person's posts score below 4. Posts with "I'm building / testing / researching" score higher. |
| Port 8000 busy | See the note at the end of section 3, Option A. |
| Connection refused / missing tables | Start PostgreSQL; check `DATABASE_URL`; run `python -m alembic upgrade head`. |
| `SEND_UNKNOWN` | Open the person → Check uncertain outcome. No match does not allow resending. |
| `HISTORY_INCOMPLETE` | X didn't return full DM history (permissions, rate limit). The queue retries later. |

---

## 18. Documents

| Document | What's in it |
|---|---|
| [docs/SUBMISSION_WRITEUP.md](docs/SUBMISSION_WRITEUP.md) | One-page write-up: approach, trade-offs, next steps, costs, AI tool use |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design with diagrams |
| [docs/VERIFICATION.md](docs/VERIFICATION.md) | What was tested, including the live test |
| [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) | Every known limit |
| [docs/COSTS.md](docs/COSTS.md) | Prices and cost estimates |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Design choices and why |
| [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) | Status of each part |
| [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) | Demo outline |
