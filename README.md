# GenAI Fund outreach on X

Find AI and robotics builders on X and start warm, personal conversations with them from your own account.

- **AI reads and writes.** It finds people from a topic or from accounts you already rate, explains why each one fits with quotes from their own posts, and drafts a short personal DM.
- **You approve every message.** Nothing is sent until you approve the exact text.
- **The app sends and tracks.** One message at a time, never twice to the same person, and replies show up under "Needs attention".

**Status:** verified end to end on real X and OpenAI on 15 Nov 2026 (two accounts controlled by the author): connect, search, AI fit, AI draft, approve, automatic send, reply, sync. Not yet run on real X: sending to people outside the test list. Details: [docs/VERIFICATION.md](docs/VERIFICATION.md).

---

## Quick start

You need **Git** and **Docker Desktop** (running). No Python, accounts or keys for the first two steps. Nothing from the author's setup is included: you choose your own password and use your own accounts and keys.

### Step 1: install and sign in

```
git clone https://github.com/ArChIt690/genai-outreach
cd genai-outreach
docker compose run --rm setup
docker compose up
```

- `docker compose run --rm setup` downloads the app (about 140 MB, from Docker Hub as [archit690/genai-outreach](https://hub.docker.com/r/archit690/genai-outreach)) and asks you to **choose a password** (12+ characters, typed twice, not shown). It writes a `.env` settings file in this folder. `.env` is ignored by git.
- `docker compose up` starts the database and the app. Wait for "Application startup complete".

Open **http://127.0.0.1:8000** and sign in with your password.

### Step 2: try it on synthetic data

The app starts in **synthetic mode**: five made-up people and a pretend X. Nothing reaches X; a yellow banner says so on every page.

1. Open `.env` in any text editor and change:
   ```
   OUTREACH_POLICY=operator_approved
   ```
   Optional, to see the AI: also set `DRAFT_PROVIDER=openai` and `OPENAI_API_KEY=your-key` (only the made-up posts are sent). Without a key you get keyword ranking and a template draft.
2. Restart: `Ctrl+C`, then `docker compose up`.
3. **Settings:** fill in "Who is writing, and why?", **tick the 30-day history box**, Save. (The send queue waits until this box is ticked.)
4. **Discover:** search `robotics, embodied AI`. Each person shows a fit, a reason and quotes.
5. **Draft for top matches** → you land on **Review**. Read a draft, edit it or Rewrite it, then **Approve and queue**.
6. **Activity:** the status turns **sent** within about 30 seconds.
7. Open that person's page → type under "Synthetic recipient reply" → **Add fixture reply** → back in Activity click **Sync all now**. The row moves to **Needs attention**.

### Step 3: test it on real X with your own two accounts

This is exactly how the author tested it. You message **a second X account that you control**, so no stranger can be reached while you test. It costs about USD 0.10 to 0.20 of X credits and less than one cent of AI.

**You need:**

- An X developer account with credits (pay-per-use, in the X Developer Console).
- Your **sending** X account (the one messages should come from, e.g. the fund's account).
- A **second** X account that you control (the test recipient).
- An OpenAI API key (or Gemini, see "All settings").

#### 3.1 Set up the X app

In the [X Developer Console](https://developer.x.com), open your app.

1. Click **Settings** (top right of the app) and find **User authentication settings**. Click **Set up** (or **Edit**) and fill in:

   | Field | Value |
   |---|---|
   | App permissions | **Read and write and Direct message** |
   | Type of App | **Web App, Automated App or Bot** (confidential client) |
   | Callback URI / Redirect URL | `http://127.0.0.1:8000/oauth/x/callback` |
   | Website URL | any URL of yours, e.g. your GitHub profile |

   Save. If **Keys and Tokens** shows your Access Token as **"Read"** only, the Direct message permission is still missing and the app will not be able to send.
2. Go to **Keys and Tokens**, scroll down past "OAuth 1.0 Keys" to **OAuth 2.0 Keys**, and copy the **Client ID** and the **Client Secret** (click Generate or Regenerate if needed; the secret is shown only once). You do **not** need the Bearer Token, Consumer Key or Access Token.
3. Check that the project has credits (**Billing → Credits**).

Never paste these keys into chats or commit them; they only go into `.env`.

#### 3.2 Switch the app to live mode

1. Stop the app (`Ctrl+C`) and delete the synthetic data (live data needs a fresh database):
   ```
   docker compose down -v
   ```
2. Open `.env` and **edit the existing lines** (don't add duplicates), then save:
   ```
   APP_MODE=live
   X_CLIENT_ID=paste-your-client-id
   X_CLIENT_SECRET=paste-your-client-secret
   OUTREACH_POLICY=test_allowlist
   AUTO_SYNC_MINUTES=0
   DRAFT_PROVIDER=openai
   OPENAI_API_KEY=paste-your-openai-key
   ```
   - `OUTREACH_POLICY=test_allowlist`: only accounts on your test list can be messaged. Right now that is nobody.
   - `AUTO_SYNC_MINUTES=0`: no background reply checks while testing (they cost X credits). You'll use the "Sync all now" button instead.
3. Start again:
   ```
   docker compose up
   ```
4. Open http://127.0.0.1:8000 and sign in. The top bar must say **Live mode**. If it still says "Fixture mode", `.env` wasn't saved or the app wasn't restarted.

#### 3.3 Connect your sending account

1. Go to **Settings** and click **Connect with X** (under "Sender connection"). This button only appears in live mode.
2. X asks you to approve the app. Sign in as your **sending** account, **not** the second one, and approve.
3. Back in the app, Settings shows your handle as **Authorized**.

The top bar still says **"Test list only"**. That is correct: nobody can be messaged until you add your second account to the test list.

#### 3.4 Say who is writing, and why

In **Settings → "Who is writing, and why?"**:

1. **Sender name:** how messages introduce you, e.g. `Archit from GenAI Fund`. The default "Prototype operator" would end up in your message.
2. **Purpose of contact:** one true line about why you are reaching out, e.g. `I'm exploring early-stage AI and robotics builders for GenAI Fund and would love to hear what you're working on.`
3. Tick **"I understand that X history is limited to 30 days"**. The send queue waits until this is ticked.
4. Click **Save sender details**.

How the message is put together: the AI writes the whole DM itself. Your purpose line says why **you** are writing and is the same for everyone. The personal part says why you are writing to **this person** and comes from their own posts:

> "Hi Sam, **I saw you're testing a tidewater gripper on low-cost robot arms** *(from their post)*. **I'm Archit from GenAI Fund and I talk to early robotics builders** *(your purpose)*. How is the grip holding up so far? Reply STOP to opt out."

Do this step before 3.5: changing the sender name or purpose later deliberately cancels earlier test consent, and you would have to record it again.

#### 3.5 Put your second account on the test list

1. Make your two accounts **follow each other** on X.
2. The test list needs the second account's **numeric ID**, not its @handle. With the app running, open a second terminal in the same folder and run (one X profile read, about USD 0.01):
   ```
   docker compose exec app python -m scripts.x_user_id @your_second_handle
   ```
   It prints the ID and the exact line to add.
3. Put that line in `.env`, save, and restart (`Ctrl+C`, then `docker compose up`):
   ```
   TEST_RECIPIENT_IDS=1234567890123456789
   ```
4. In **Settings → Register a test recipient**:
   - X handle: your second account's handle
   - Consent reference: `My own second account, controlled by me`
   - Tick **"I control this recipient account"** and click **Record test consent** (one X profile read, about USD 0.01).

#### 3.6 Post a test post from the second account

Logged in to X as your **second** account, post exactly:

> I'm testing a tidewater gripper on low-cost robot arms this week.

- "tidewater gripper" is a rare phrase, so your search finds only this post, and the search costs almost nothing.
- "I'm testing" (or building / researching / developing) gives the post enough evidence for the app to draft. A bare mention scores too low.

#### 3.7 Search

1. Go to **Discover**. Leave **Role signals** and **Location term** empty.
2. In **Topics** type `tidewater gripper` and click **Find relevant people**.
3. Your second account appears with a score, and the AI's judgment: a **fit** (e.g. strong / builder), a **reason**, and your post **quoted word for word**. This is the first X search and the first AI call.

If something looks wrong:

- **"No matching public evidence"**: X can take 10 to 15 minutes to make a new post searchable. Wait and search again.
- **"AI fit judging returned nothing usable" / "was unavailable"**: the AI call failed. Open **Settings → AI usage**: the newest row shows the error code. `HTTP_401` means the key was refused: check `OPENAI_API_KEY` in `.env` (and, if you run without Docker, that no old key is set in your system environment).

#### 3.8 Draft and review

1. Click **Draft for top matches**. You land on **Review** with one card for your second account.
2. Read the draft against the post shown above it. It should mention the gripper post, say who is writing and why, ask one question, and end with a STOP line. Above the text box, "Draft relies on" shows the exact quote the AI used.
3. Optional: edit the text, or type a note such as `shorter` and click **Rewrite with gpt-6.1-terra** for a new version.
4. If the card says **"This person cannot be queued: consent required"**, you changed the sender name or purpose after recording consent: repeat step 3.5.4.

#### 3.9 Send

Click **Approve and queue**. This approves exactly the text in the box and sends a **real DM** from your sending account to your second account within about 30 seconds.

Open **Activity**: the status turns **sent**. If it says "Queued" with a hold reason instead, the reason is shown in plain words (for example the 30-day history tick from 3.4).

#### 3.10 Find the message and reply

1. Log in to X as your **second** account and open **Chat**.
2. If the conversation isn't in the list, open **Requests**. Messages from accounts the recipient doesn't follow land there. Following back helps future messages arrive in the main list.
3. Open the message and reply, e.g. *"Thanks, happy to chat."*

#### 3.11 Sync the reply

In the app go to **Activity** and click **Sync all now**. The row moves to **Needs attention**, and the person's page shows both messages. **The live test is complete.**

---

## Step 4: real outreach (what the app is for)

Do this only after Step 3 worked, and only once your organisation has decided to run this outreach from its own account.

#### 4.1 Switch the send rule

1. In `.env` set:
   ```
   OUTREACH_POLICY=operator_approved
   ```
2. Choose the pace (these are the defaults):
   ```
   DAILY_SEND_LIMIT=10
   SEND_MIN_GAP_SECONDS=120
   AUTO_SYNC_MINUTES=180
   ```
   `AUTO_SYNC_MINUTES` checks replies automatically for 14 days after each send, at about USD 0.01 per conversation per check (about USD 1.12 per conversation at 180). Use 720 to spend less, or 0 to check only with "Sync all now".
3. Restart (`Ctrl+C`, then `docker compose up`). The top bar and Settings now say **Operator-approved sending**.

What changes: anyone the app finds can be messaged **once you approve the exact text**. What stays enforced: your approval of every single message; nobody ever gets a second first message; the do-not-contact list and STOP replies; the pause button; the daily limit, the gap between sends and the budget cap (`X_BUDGET_USD`); a fresh re-read of the quoted posts before each send.

#### 4.2 Find the people you want to reach

On **Discover**, either:

- **Describe the segment:** one to five topics, e.g. `embodied AI, robot learning, manipulation`. Optionally add role signals (`founder, researcher`) or a location term (`Singapore`). Location is a search word, not a verified place.
- **Or start from accounts you already rate:** under "Or start from accounts you already rate", enter one to three handles of builders you like and click **Find similar people**. The AI describes what they work on and searches for people doing similar work; the seeds themselves are left out.

Each person gets a fit (strong, possible, weak), a role, a reason and quotes from their own posts. News and company accounts are marked "not a person". Click a name to see all their evidence.

#### 4.3 Draft, review, approve

1. Click **Draft for top matches**. The AI drafts a personal DM for every strong or possible match (up to 10). Nothing is sent.
2. On **Review**, go through each card:
   - Check the reason and the quotes against the source posts.
   - **Approve and queue** the ones you'd send as written (or after editing the text).
   - **Rewrite** with a note if the tone or focus is off.
   - **Skip** people you don't want to contact now; **Do not contact** to block someone permanently.

#### 4.4 Let it send

Approved messages go out one at a time, `SEND_MIN_GAP_SECONDS` apart, up to `DAILY_SEND_LIMIT` a day, while the app is running. **Activity** shows each message's place in the queue and why it's waiting, if it is. **Settings → Pause new sends** stops everything instantly.

#### 4.5 Follow up on replies

- Replies are checked automatically (every `AUTO_SYNC_MINUTES`) or with **Activity → Sync all now**.
- **Activity → Needs attention** lists new replies, messages X refused (e.g. the person accepts DMs only from people they follow) and anything uncertain.
- Open a person's page to read the conversation, then **continue the conversation in X** itself. Click **Mark replies handled** when done.
- A reply of **STOP** puts the person on the do-not-contact list automatically.
- **Settings → AI usage** shows every AI call; the X spend estimate is next to the limits.

To go back to testing: set `OUTREACH_POLICY=test_allowlist` and restart. Queued messages to people not on the test list leave the queue with a note; none are sent.

---

## What it does, against the brief

| The brief asks for | How the tool does it |
|---|---|
| Start from a target segment **or seed accounts** | Type topics, or enter 1 to 3 X handles you already rate; the AI turns the seeds' posts into searches for people doing similar work. |
| Find people and **explain why they fit** | One X search, a keyword score, then the AI judges the top 10 (strong, possible, weak) with a reason and quotes, each checked word for word against the person's posts. |
| **Personalised** DMs from **real evidence** | Each draft mentions something the person actually posted. Drafts with made-up quotes, links, no opt-out line or over 500 characters are rejected. |
| Drafts **for us to review and approve** | Review page: reason, quotes, source posts, editable text. Approve, edit, rewrite with a note, skip, or do-not-contact. |
| Send from **our connected account** within X's rules | Your own account via X's official sign-in. One message at a time, 2 minutes apart, at most 10 a day (adjustable). |
| **Never double-messages** | One record per person, a check of past DMs, no automatic retries, a stored key per message so a restart can't resend. |
| Show **sent, replied, needs attention** | Activity: status, place in the queue, replies. Replies are checked automatically or with "Sync all now". |
| Usable **without the author** | This README, a synthetic mode to practise in, and a plain-words reason on screen for every hold or block. |

![Review page: the AI's reason, the quotes and the editable draft](docs/screenshots/review.png)

---

## Details

Click a section to open it.

<details>
<summary><b>What you need for real use (accounts, API access, costs)</b></summary>

| Need | Details |
|---|---|
| X developer account with credits | Pay-per-use credits in the X Developer Console. About USD 5 covers testing and a demo comfortably. |
| An X app with user sign-in | See Step 3.1. Permission "Read and write and Direct message". |
| The X account messages are sent from | Connected inside the app; its token is stored encrypted. |
| For testing: a second X account you control | Real test messages may only go to accounts you control or people who agreed. |
| An AI key (recommended) | OpenAI (`gpt-6-luna`, backup and rewrites `gpt-6.1-terra`) or Google Gemini. Without one: keyword ranking and template drafts. |
| Software | Git and Docker Desktop. Or Python 3.12 and PostgreSQL 16+ (see "Running without Docker"). |

</details>

<details>
<summary><b>Using it day to day</b></summary>

1. **Discover:** topics (one to five, comma separated) or one to three seed accounts. Ordered strong, possible, unjudged, weak.
2. **Draft for top matches:** drafts for every strong or possible person, up to 10, skipping anyone already contacted, blocked or drafted. Nothing is sent.
3. **Review**, per card:
   - **Approve and queue:** approves exactly the text in the box.
   - **Save edit:** keeps your changes without approving.
   - **Rewrite:** a new draft from the same posts by the stronger model; add a note like "shorter".
   - **Skip:** hides the draft without blocking the person.
   - **Do not contact:** blocks the person permanently.
4. **Activity:** every message, its status, place in the queue, hold reason and replies. **Needs attention** shows new replies, refused messages and anything uncertain. **Sync all now** checks replies immediately.
5. **Person page:** the evidence, the full conversation, send history, "Mark replies handled".
6. **Settings:** pause or resume, send rule and limits, X spend estimate, **AI usage** (every AI call with model, tokens, time and result), purge of stored text.

A reply of "STOP" adds the person to the do-not-contact list automatically.

</details>

<details>
<summary><b>How it never double-messages</b></summary>

- **One record per person:** the database allows only one outreach record per sender and recipient.
- **Past DMs are checked** before sending; any earlier message from you blocks the send.
- **No automatic retries:** an unclear answer from X marks the message "unknown", holds the sender and stops the queue until a person checks it ("Check uncertain outcome").
- **A stored key per message,** saved when you approve: after a crash or restart the app finds the stored result instead of sending again.
- **Database locks:** two sends of the same message at the same moment cannot both go through.

</details>

<details>
<summary><b>Blocked actions and what to do</b></summary>

Every block shows its reason on screen.

| You see | Why | What to do |
|---|---|---|
| Queue holding: **history acknowledgement required** | 30-day history box not ticked | Settings → tick → Save |
| Queue holding: **pacing** | Less than `SEND_MIN_GAP_SECONDS` since the last send | Wait |
| Queue holding: **daily limit** | `DAILY_SEND_LIMIT` reached (UTC day) | Wait, or raise the limit |
| Queue holding: **rate limited** | X asked to slow down | Wait; it retries after X's time (or 15 minutes) and keeps your approval |
| Queue holding: **sending paused / disabled** | Pause button, or `SEND_ENABLED=false` | Settings → Resume, or set `SEND_ENABLED=true` |
| Queue holding: **sender busy** | A previous send had an unknown outcome | Person page → Check uncertain outcome, or Freeze this contact |
| **recipient not allowed** | Test-list rule, person not in `TEST_RECIPIENT_IDS` | Expected while testing |
| **consent required** | Test-list rule, no valid consent (or purpose changed) | Settings → Register a test recipient again |
| **do not contact** | You blocked them, or they replied STOP | None; permanent |
| **already contacted** | You messaged them before (here or on X) | None; continue in X |
| **approval stale** | Text changed in another tab | Refresh, approve again |
| **budget exceeded** | `X_BUDGET_USD` reached (app's estimate) | Check X billing, raise the cap |
| Rejected: **X permission or recipient restricted** | Person only accepts DMs from people they follow, or the app lacks DM permission | Nothing for that person; check app permissions if it happens to everyone |
| "AI fit judging was unavailable" / draft labelled **fallback** | AI call failed or its answer failed the checks | Settings → AI usage shows the code; the app continues without AI |

</details>

<details>
<summary><b>Limitations</b></summary>

- Cold DMs usually land in the recipient's **Requests**. People who accept DMs only from accounts they follow can't be reached (X refuses; the app marks it rejected). The app never follows anyone to get around this.
- Search covers X's **last seven days**; seed accounts must have posted in that window.
- DM history covers **30 days**, so older messages sent outside this app can't be seen.
- Seed accounts find **similar** people, not the seed's followers or contacts.
- The AI judges only the **top 10** keyword matches per search.
- Quote checks prove the quotes are real, not that the AI's summary is fair: you still read each draft.
- One operator and one sending account; run one app process.
- The daily limit and gap are our caution, not verified X quotas.
- Not yet run on real X: operator-approved sending, and Rewrite with `gpt-6.1-terra`.

Full list: [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md).

</details>

<details>
<summary><b>X rules this tool follows</b></summary>

- Official X API only: no scraping, browser automation or bypassing restrictions.
- A person approves every message.
- One message at a time, a minimum gap, a daily cap; X's rate limits and reset times are respected.
- No automatic follows, likes, retries or follow-up messages.
- Every message has an opt-out line; a STOP reply blocks further contact.
- Only public profile text and public posts go to the AI; never DMs or tokens.
- Tokens are stored encrypted; secrets live only in `.env`, which git ignores.

</details>

<details>
<summary><b>Costs</b></summary>

Paid tools: the X API (pay per use) and OpenAI (or Gemini). No hosting needed.

| Action | Expected cost |
|---|---|
| One search (up to 50 posts, 20 people) | up to about USD 0.45; a narrow search costs cents |
| One seed account | about USD 0.06, plus the search |
| One approved message | about USD 0.05 |
| Reply checks | about USD 0.01 per conversation per check |
| AI: one search judged plus ten drafts (`gpt-6-luna`) | about USD 0.001 to 0.01 |
| AI: one Rewrite (`gpt-6.1-terra`) | about USD 0.001 to 0.01 |
| **The author's full live test** | **about USD 0.18 of X, under 1 cent of AI** |

Example day at the defaults: one search and ten messages cost about USD 1 of X, plus up to about USD 11 of reply checks over the next 14 days (raise `AUTO_SYNC_MINUTES` or set it to 0 to cut this). Caps: `X_BUDGET_USD` (default 5), `AI_DAILY_CALL_LIMIT` (200 a day), `DAILY_SEND_LIMIT`. Prices from November 2026; check current prices. Details: [docs/COSTS.md](docs/COSTS.md).

</details>

<details>
<summary><b>How it works</b></summary>

One Python web app (FastAPI) and one PostgreSQL database. All AI calls go through one module that tries a backup model when the first is busy, caps daily calls and logs every call. A background thread inside the app sends approved messages at the set pace and checks for replies; the send function re-checks every rule immediately before each send.

Diagrams: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

</details>

<details>
<summary><b>All settings</b> (in <code>.env</code>; restart after changes)</summary>

| Setting | Default | Meaning |
|---|---|---|
| `APP_MODE` | fixture | `fixture` (synthetic) or `live` (real X). Each needs its own database. |
| `DATABASE_URL` | local | PostgreSQL connection. Docker sets this for you. |
| `APP_ORIGIN` / `X_CALLBACK_URL` | 127.0.0.1:8000 | Must match the browser address and the X app. |
| `X_CLIENT_ID` / `X_CLIENT_SECRET` | empty | Your X app's OAuth 2.0 keys. |
| `SEND_ENABLED` | true after setup | Master switch for sending. |
| `OUTREACH_POLICY` | test_allowlist | Who can be messaged. |
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
| `WORKER_ENABLED` | true | false stops automatic sending and reply checks. |
| `X_BUDGET_USD` | 5 | Cap on the app's estimate of X spend. |
| `HISTORY_LIMIT_ACKNOWLEDGED` | false | Same as ticking the 30-day history box. |

Sender name, purpose, the history tick, the connected account and test consent are set on the Settings page.

</details>

<details>
<summary><b>Docker commands</b></summary>

- Stop: `Ctrl+C` or `docker compose down`. Start again: `docker compose up`.
- Delete all data (e.g. to switch between synthetic and live): `docker compose down -v`.
- Newest published image: `docker compose pull`, then `docker compose up`.
- Run your own local code changes instead: `docker compose up --build`.
- Change your password: `docker compose run --rm setup python -m scripts.bootstrap --reset-password`, then restart.
- Find an account's numeric X ID (live mode, app running): `docker compose exec app python -m scripts.x_user_id @handle`.
- Port 8000 busy: change `"127.0.0.1:8000:8000"` in `compose.yaml` (e.g. to `"127.0.0.1:8080:8000"`) and set `APP_ORIGIN=http://127.0.0.1:8080` and `X_CALLBACK_URL=http://127.0.0.1:8080/oauth/x/callback` in `.env`.
- Linux, if `.env` can't be written: `docker compose run --rm --user "$(id -u):$(id -g)" setup`.

</details>

<details>
<summary><b>Running without Docker</b> (Python 3.12 and PostgreSQL 16+)</summary>

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock
createdb -U <your postgres user> outreach
.venv\Scripts\python.exe -m scripts.bootstrap --fixture-demo --database-url "postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/outreach"
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

- On macOS or Linux use `.venv/bin/python`. On Windows with several Pythons: `py -3.12 -m venv .venv`.
- For live mode use a separate database (e.g. `outreach_live`) and point `DATABASE_URL` at it.
- Keep `--no-access-log` (stops X sign-in codes from reaching logs). Run one app process.
- If `OPENAI_API_KEY` or `GEMINI_API_KEY` is also set in your system environment, it overrides `.env`; remove it and restart from a new terminal.
- Numeric X ID for the test list: `.venv\Scripts\python.exe -m scripts.x_user_id @handle`.

</details>

<details>
<summary><b>Tests</b></summary>

258 automated tests, including real-database concurrency tests and two browser tests. They use synthetic data and fake AI and X servers, never call real services, and strip real keys from their environment. Needs the Python setup above.

```
$env:TEST_DATABASE_URL="postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/outreach_test"
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check .
```

The test database name must start with `outreach_test` (it is emptied each run). Browser tests use Microsoft Edge on Windows or `BROWSER_EXECUTABLE`; skip them with `-m "not browser"`.

</details>

<details>
<summary><b>Troubleshooting</b></summary>

| Problem | Fix |
|---|---|
| No "Connect with X" button | `APP_MODE` is still `fixture`. Set `live` and restart (Docker: `docker compose down -v` first). |
| `MODE_MISMATCH` on start | The database belongs to the other mode. Docker: `docker compose down -v`. Otherwise use a separate database. |
| AI calls fail with `HTTP_401` | The provider refused the key. Without Docker, a key in your system environment overrides `.env`. |
| Sent DM not visible to the recipient | X shows DMs under Chat; messages from accounts they don't follow go to Requests. |
| New post not found by search | X can take 10 to 15 minutes to make a new post searchable. |
| "Insufficient professional evidence" when drafting | The posts score below 4. First-person posts ("I'm building / testing / researching") score higher. |
| Port 8000 busy | See "Docker commands". |
| `SEND_UNKNOWN` | Person page → Check uncertain outcome. No match does not allow resending. |
| `HISTORY_INCOMPLETE` | X didn't return full DM history (permissions, rate limit). The queue retries later. |

</details>

<details>
<summary><b>For the maintainer: publishing a new image</b></summary>

After code changes, from a clean checkout of committed code (needs `docker login` as the image owner):

```
docker buildx build --platform linux/amd64,linux/arm64 -t archit690/genai-outreach:latest --push .
```

</details>

---

## Documents

| Document | What's in it |
|---|---|
| [docs/SUBMISSION_WRITEUP.md](docs/SUBMISSION_WRITEUP.md) | One-page write-up: approach, trade-offs, next steps, costs, AI tool use |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design with diagrams |
| [docs/VERIFICATION.md](docs/VERIFICATION.md) | What was tested, including the live test |
| [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) | Every known limit |
| [docs/COSTS.md](docs/COSTS.md) | Prices and cost estimates |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Design choices and why |
| [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) | Status of each part |
