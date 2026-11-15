# GenAI Fund – X outreach prototype

A working tool for finding AI and robotics builders on X and starting warm, personal DM conversations with them from your own X account.

You give it a **target segment** (topics) or **seed accounts** (people you already rate). It:

1. finds people on X and **explains why each one fits**, quoting their own posts;
2. **drafts a personal DM** for each one, based only on what they actually posted;
3. waits for **you to review and approve** every message;
4. **sends** approved messages from your connected account, one at a time, within limits;
5. **never messages anyone twice**;
6. shows **what was sent, who replied and what needs your attention**.

It was tested end to end on real X and OpenAI with two accounts controlled by the author. Sending to people outside a test list has not been run on real X yet. See [docs/VERIFICATION.md](docs/VERIFICATION.md).

---

## What you need

| | Needed for | Notes |
|---|---|---|
| **Git** and **Docker Desktop** | Everything | Docker Desktop must be running. No Python needed. |
| **X developer account with credits** | Real X | Pay-per-use credits in the [X Developer Console](https://developer.x.com). USD 5 is plenty for testing. |
| **Your sending X account** | Real X | The account messages will come from, e.g. the fund's account. |
| **A second X account you control** | The test | Real test messages may only go to accounts you control or people who agreed. |
| **OpenAI API key** | AI judging and drafting | Uses `gpt-6-luna` for everyday work and `gpt-6.1-terra` as backup and for rewrites. Without a key the app still works, with keyword ranking and a template draft. |

Nothing from the author's setup is included. You choose your own password and use your own accounts and keys. All of them stay in a local `.env` file that git ignores.

**Costs:** the full test below costs about USD 0.10 to 0.20 of X credits and less than one cent of OpenAI. Real outreach costs are under [Costs](#costs).

---

## Part 1: Install

```
git clone https://github.com/ArChIt690/genai-outreach
cd genai-outreach
docker compose run --rm setup
docker compose up
```

- `docker compose run --rm setup` downloads the app from Docker Hub ([archit690/genai-outreach](https://hub.docker.com/r/archit690/genai-outreach)) and asks you to **choose a password** (at least 12 characters, typed twice, not shown on screen). It creates the `.env` settings file in this folder.
- `docker compose up` starts the database and the app. Wait until you see "Application startup complete". Leave this terminal open; the app runs as long as it is open.

Open **http://127.0.0.1:8000** and sign in with your password.

The app starts in **fixture mode**: five made-up people and a pretend X, so you can look around safely. Every page shows a yellow "Synthetic workspace" banner. Nothing reaches X.

To restart the app at any point: press `Ctrl+C` in that terminal, then run `docker compose up` again. The app reads `.env` only when it starts.

---

## Part 2: Test it on real X with your two accounts

This is the exact sequence the author used. Your sending account messages your **second** account, and the app is set so that **nobody else can be messaged**.

### Step 1: Set up your X app

In the [X Developer Console](https://developer.x.com), open your app.

1. Click **Settings** (top right of the app) and find **User authentication settings**. Click **Set up** or **Edit** and fill in:

   | Field | Value |
   |---|---|
   | App permissions | **Read and write and Direct message** |
   | Type of App | **Web App, Automated App or Bot** (confidential client) |
   | Callback URI / Redirect URL | `http://127.0.0.1:8000/oauth/x/callback` |
   | Website URL | any URL of yours, e.g. your GitHub profile |

   Save. This step matters: if **Keys and Tokens** shows your access token as **"Read"** only, the app can't send DMs.

2. Go to **Keys and Tokens** and scroll down past "OAuth 1.0 Keys" to **OAuth 2.0 Keys**. Copy:
   - **Client ID**
   - **Client Secret** (click Generate or Regenerate if needed; it is shown only once)

   You don't need the Bearer Token, the Consumer Key or the Access Token. The app gets its own token when you click "Connect with X".

3. Check the project has credits under **Billing → Credits**.

Keep the Client ID and Secret to yourself. They only go into `.env`.

### Step 2: Switch the app to live mode

1. Stop the app (`Ctrl+C`) and delete the fixture data. Live mode needs a fresh database:
   ```
   docker compose down -v
   ```
2. Open `.env` in a text editor (Windows: `notepad .env`, macOS: `open -e .env`). **Change the existing lines** to these values (don't add a second copy of a line), then save:
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
   - `AUTO_SYNC_MINUTES=0`: no automatic background reply checks while testing, since each check costs X credits. You'll use the **Sync all now** button instead.
3. Start the app again:
   ```
   docker compose up
   ```
4. Open http://127.0.0.1:8000 and sign in with the same password. The top bar must say **Live mode**. If it still says "Fixture mode", `.env` wasn't saved or the app wasn't restarted.

### Step 3: Connect your sending account (Settings)

1. Go to **Settings**. Under **Sender connection**, click **Connect with X**. The button only appears in live mode.
2. X asks you to approve the app. Sign in to X as your **sending** account (not the second one) and approve.
3. Back in the app, Settings shows your handle with **Authorized** next to it.

The top bar says **Test list only**. That's correct: nobody can be messaged until your second account is on the test list.

### Step 4: Say who is writing, and why (Settings)

In **Settings → "Who is writing, and why?"**:

1. **Sender name or organization:** how messages should introduce you, e.g. `Archit from GenAI Fund`. Change it: the default "Prototype operator" would appear in your message.
2. **Honest purpose of contact:** one true line about why you are reaching out, e.g. `I'm exploring early-stage AI and robotics builders for GenAI Fund and would love to hear what you're working on.`
3. Tick **"I understand that X history is limited to 30 days…"**. The send queue waits until this is ticked.
4. Click **Save sender details**.

**Why the purpose line, if the AI writes the message?** The AI writes the whole message, but it must not make up why you are writing. The two parts of a message come from different places:

| | Purpose of contact | Personal touch |
|---|---|---|
| Answers | Why are **you** writing? | Why are you writing to **this person**? |
| Comes from | You, typed once here | The AI, from each person's own posts |
| Same for everyone? | Yes | No |

> "Hi Sam, **I saw you're testing a tidewater gripper on low-cost robot arms** *(personal touch)*. **I'm Archit from GenAI Fund and I talk to early robotics builders** *(your purpose)*. How is the grip holding up so far? Reply STOP to opt out."

Do this step **before** Step 5. Changing the sender name or purpose later deliberately cancels earlier test consent, and you would have to record it again.

### Step 5: Add your second account to the test list (Settings)

1. On X, make your two accounts **follow each other**.
2. The test list needs your second account's **numeric ID**, not its @handle. With the app running, open a **second** terminal in the same folder and run:
   ```
   docker compose exec app python -m scripts.x_user_id @your_second_handle
   ```
   It makes one X profile read (about USD 0.01) and prints the ID and the exact line to add.
3. Add that line to `.env`, save, and restart the app (`Ctrl+C`, then `docker compose up`):
   ```
   TEST_RECIPIENT_IDS=1234567890123456789
   ```
4. In **Settings → Register a test recipient**, fill in:
   - **X handle:** your second account's handle
   - **Consent reference:** `My own second account, controlled by me`
   - Tick **"I control this recipient account and authorize a single prototype test message"**
   - Click **Record test consent** (one X profile read, about USD 0.01).

### Step 6: Post a test post from your second account

Logged in to X as your **second** account, post exactly this:

> I'm testing a tidewater gripper on low-cost robot arms this week.

The wording matters for two reasons:

- **"tidewater gripper" is a rare phrase,** so your search finds only this post and costs almost nothing.
- **"I'm testing" earns enough evidence** for the app to allow an AI draft ("I'm building / researching / developing" work too). A bare mention scores too low.

### Step 7: Search (the first real X search and AI call)

1. Go to **Discover**. Leave **Role signals** and **Location term** empty.
2. In **Topics**, type `tidewater gripper` and click **Find relevant people**.
3. Your second account appears with a keyword score and the AI's judgment: a **fit** (for example *strong / builder*), a **reason**, and your post **quoted word for word**.

If it doesn't look like that:

- **"No matching public evidence in this sample":** X can take 10 to 15 minutes to make a new post searchable. Wait and search again.
- **"AI fit judging returned nothing usable" or "AI fit judging was unavailable":** the AI call failed. Open **Settings → AI usage**: the newest row shows an error code. `HTTP_401` means OpenAI refused the key; check `OPENAI_API_KEY` in `.env` and restart.

### Step 8: Draft and review

1. Click **Draft for top matches**. You land on **Review**, with one card for your second account.
2. Read the draft. The AI wrote the whole message itself: one line about your post, who is writing and why (from Step 4), one easy question, and a STOP line at the end. "Draft relies on" shows the exact quote it used.
3. Optional: edit the text yourself, or type a note such as `shorter` and click **Rewrite with gpt-6.1-terra**.
4. If the card says **"This person cannot be queued: consent required"**, you changed the sender name or purpose after Step 5. Repeat Step 5.4.

### Step 9: Send

Click **Approve and queue**. This approves exactly the text in the box and sends a **real DM** from your sending account to your second account within about 30 seconds.

Open **Activity**: the status changes to **sent**. If it says "Queued" with a hold reason instead, the reason is written there in plain words (for example, the 30-day history tick from Step 4).

### Step 10: Find the message and reply

1. Log in to X as your **second** account and open **Chat** (X's direct messages).
2. If the conversation isn't in the list, open **Requests**. Messages from accounts the recipient doesn't follow land there.
3. Open the message and reply, e.g. *"Thanks, happy to chat."*

### Step 11: Sync the reply

In the app, go to **Activity** and click **Sync all now**. The row moves to **Needs attention**, and the person's page shows both messages.

**The test is complete:** connect, search, AI judgment, AI draft, approval, automatic send, reply and tracking all worked on real X.

---

## Part 3: Real outreach

This is what the tool is for. Do it only after Part 2 worked, and once your organisation has decided to run this outreach from its own account.

### Step 1: Switch the send rule

1. In `.env`, change:
   ```
   OUTREACH_POLICY=operator_approved
   AUTO_SYNC_MINUTES=180
   ```
2. Optionally set the pace (these are the defaults):
   ```
   DAILY_SEND_LIMIT=10
   SEND_MIN_GAP_SECONDS=120
   ```
3. Restart (`Ctrl+C`, then `docker compose up`). The top bar and Settings now say **Operator-approved sending**.

**What changes:** anyone the app finds can be messaged once you approve the exact text. The test list and recorded consent are no longer required.

**What stays enforced:**

- You approve every single message.
- Nobody ever gets a second first message.
- The do-not-contact list, including automatic blocking when someone replies STOP.
- The **Pause new sends** button.
- The daily limit, the gap between sends and the X budget cap.
- A fresh re-read of the quoted posts just before each send.

### Step 2: Find the people you want to reach

On **Discover**, either:

- **Describe the segment:** one to five topics, e.g. `embodied AI, robot learning, manipulation`. Optionally add role signals (`founder, researcher`) or a location term (`Singapore`). The location term is just a search word, not a verified place.
- **Or start from accounts you already rate:** under **"Or start from accounts you already rate"**, enter one to three X handles and click **Find similar people**. The AI describes what they work on and searches for people doing similar work. The seeds themselves are left out.

Each person gets a fit (strong, possible or weak), a role, a reason and quotes from their own posts. News and company accounts are marked "not a person". Click a name to see all their evidence.

### Step 3: Draft, review and approve

1. Click **Draft for top matches**. The AI drafts a personal DM for every strong or possible match, up to 10. Nothing is sent yet.
2. On **Review**, for each card:
   - Read the reason and the quotes against the person's posts.
   - **Approve and queue** the messages you'd send, as written or after editing.
   - **Rewrite** with a note if the tone or focus is off.
   - **Skip** people you don't want to contact now.
   - **Do not contact** blocks someone permanently.

### Step 4: Let it send

While the app is running, approved messages go out one at a time: at least `SEND_MIN_GAP_SECONDS` apart and at most `DAILY_SEND_LIMIT` per day. **Activity** shows each message's place in the queue, and the reason whenever it's waiting. **Settings → Pause new sends** stops sending immediately.

### Step 5: Handle replies

- Replies are checked automatically every `AUTO_SYNC_MINUTES` (for 14 days after each send), or immediately with **Activity → Sync all now**.
- **Activity → Needs attention** lists new replies, messages X refused (for example, the person only accepts DMs from accounts they follow) and anything uncertain.
- Open the person's page to read the conversation, **continue it in X**, then click **Mark replies handled**.
- A reply of **STOP** puts the person on the do-not-contact list automatically.
- **Settings → AI usage** lists every AI call; the X spend estimate is shown next to the limits.

To go back to testing, set `OUTREACH_POLICY=test_allowlist` and restart. Queued messages to people not on the test list leave the queue with a note; none are sent.

---

## When something is blocked

The app always shows the reason on screen.

| You see | Why | What to do |
|---|---|---|
| Queue holding: **history acknowledgement required** | The 30-day history box isn't ticked | Settings → tick it → Save sender details |
| Queue holding: **pacing** | Less than `SEND_MIN_GAP_SECONDS` since the last send | Nothing; it continues by itself |
| Queue holding: **daily limit** | `DAILY_SEND_LIMIT` reached (UTC day) | Wait for the next day, or raise the limit |
| Queue holding: **rate limited** | X asked the app to slow down | Nothing; it retries later and keeps your approval |
| Queue holding: **sending paused** | The pause button is on | Settings → Resume new sends |
| Queue holding: **sender busy** | A previous send had an unclear result | Open that person → **Check uncertain outcome**, or **Freeze this contact** |
| **recipient not allowed** | Test-list rule is on and this person isn't on it | Expected while testing; see Part 3 |
| **consent required** | Test-list rule: no consent, or the purpose changed | Settings → Register a test recipient again |
| **do not contact** | You blocked them, or they replied STOP | Nothing; this is permanent |
| **already contacted** | You messaged them before, here or on X | Nothing; continue in X |
| **approval stale** | The text changed in another tab | Refresh and approve again |
| **budget exceeded** | The app's X spend estimate reached `X_BUDGET_USD` | Check X billing, then raise the cap in `.env` |
| Rejected: **X permission or recipient restricted** | The person only accepts DMs from accounts they follow | Nothing to do for that person |

---

## How it never double-messages

- **One record per person:** the database allows only one outreach record per sender and recipient.
- **Past DMs are checked** before sending; any earlier message from you blocks the send.
- **No automatic retries:** if X's answer is unclear, the message is marked "unknown" and sending stops until a person checks it.
- **A stored key per message,** saved at approval: after a crash or restart the app finds the stored result instead of sending again.
- **Database locks:** two sends of the same message at the same moment can't both go through.

---

## X rules it follows

- The official X API only: no scraping, browser automation or bypassing restrictions.
- A person approves every message.
- One message at a time, with a minimum gap and a daily cap; X's rate limits are respected.
- No automatic follows, likes, retries or follow-up messages.
- Every message has an opt-out line, and a STOP reply blocks further contact.
- Only public profile text and public posts go to the AI; never DMs or tokens.

---

## Costs

Paid tools: the **X API** (pay per use) and **OpenAI**. Nothing is hosted; it runs on your computer.

| Action | Approximate cost |
|---|---|
| One search (up to 50 posts and 20 people) | up to USD 0.45; a narrow search costs cents |
| One seed account | USD 0.06, plus the search |
| One approved message (re-check the posts and past DMs, send) | USD 0.05 |
| One reply check | USD 0.01 per conversation |
| AI for one search plus ten drafts (`gpt-6-luna`) | USD 0.001 to 0.01 |
| One rewrite (`gpt-6.1-terra`) | USD 0.001 to 0.01 |
| **The author's whole live test** | **USD 0.18 of X, under 1 cent of AI** |

Example: a day with one search and ten messages costs about USD 1 of X, plus up to about USD 11 of automatic reply checks over the next 14 days at `AUTO_SYNC_MINUTES=180` (set it higher, or to 0, to spend less). The app stops X calls when its estimate reaches `X_BUDGET_USD` (default 5) and AI calls at `AI_DAILY_CALL_LIMIT` (default 200 a day). Prices are from November 2026. Details: [docs/COSTS.md](docs/COSTS.md).

---

## Limitations

- Cold DMs usually land in the recipient's **Requests**. People who accept DMs only from accounts they follow can't be reached; the app never follows anyone to get around this.
- Search covers X's **last seven days**. Seed accounts must have posted in that window.
- DM history covers **30 days**, so very old messages sent outside this app aren't seen.
- Seed accounts find **similar** people, not the seed's followers.
- The AI judges the **top 10** keyword matches of each search.
- The quote check proves the quotes are real, not that the AI's summary is fair. You still read every draft.
- One operator and one sending account.
- The daily limit and gap are deliberate caution, not verified X quotas.
- Not yet run on real X: operator-approved sending, and rewriting with `gpt-6.1-terra`.

Full list: [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md).

---

## Troubleshooting

| Problem | Fix |
|---|---|
| No "Connect with X" button | `APP_MODE` is still `fixture`: run `docker compose down -v`, set `APP_MODE=live`, start again. |
| `MODE_MISMATCH` when starting | The database belongs to the other mode: `docker compose down -v`, then start again. |
| AI calls fail with `HTTP_401` | OpenAI refused the key. Check `OPENAI_API_KEY` in `.env` and restart. |
| Sent DM not visible to the recipient | Look in **Chat → Requests** on the recipient account. |
| New post not found by search | Wait 10 to 15 minutes; X needs time to index new posts. |
| "Insufficient professional evidence" when drafting | The posts score too low. First-person posts ("I'm building / testing / researching") score higher. |
| Port 8000 is busy | In `compose.yaml` change `"127.0.0.1:8000:8000"` to e.g. `"127.0.0.1:8080:8000"`, and set `APP_ORIGIN=http://127.0.0.1:8080` and `X_CALLBACK_URL=http://127.0.0.1:8080/oauth/x/callback` in `.env` and in the X app. |
| Forgot the password | `docker compose run --rm setup python -m scripts.bootstrap --reset-password`, then restart. |

---

## More

| | |
|---|---|
| [docs/SUBMISSION_WRITEUP.md](docs/SUBMISSION_WRITEUP.md) | One-page write-up: approach, trade-offs, next steps, costs, AI tool use |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How it works, with diagrams |
| [docs/VERIFICATION.md](docs/VERIFICATION.md) | What was tested, including the live test |
| [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) | Every known limitation |
| [docs/COSTS.md](docs/COSTS.md) | Prices and cost estimates |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Design choices and why |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Running without Docker, tests, publishing the image |
| [.env.example](.env.example) | Every setting, with comments |
