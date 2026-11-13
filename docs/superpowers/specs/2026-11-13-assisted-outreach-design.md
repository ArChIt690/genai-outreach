# Design: AI-assisted outreach with a human approval gate

Date: 13 Nov 2026. Deadline for the whole submission: 17 Nov 2026, 10:30 AM IST.

## Why

The assignment says: *"If we can't use it to run outreach ourselves, it doesn't pass."* Today the app fails that in three ways:

1. It refuses to message anyone it discovers. Only a pre-set test list can be messaged.
2. Every step is a manual click for one person at a time, so it doesn't work "at scale".
3. Fit is judged by keyword rules and messages come from a paste-in template, which is weak for "relevant targeting" and "thoughtful personalisation".

The strongest part of the app is its safety core: one record per person, exact-text approval, no automatic retries, a check of past DM history. That stays unchanged.

## Goals

- GenAI Fund can message discovered people once a human has approved the exact text.
- AI does the reading and writing: it judges fit, explains why with quoted posts, and drafts the message.
- A human approves, edits or skips each draft in one review queue.
- After approval the app sends at a safe pace and checks for replies without being asked.
- Every AI call is visible: tokens, speed, errors.

## Not in this round

- Sending without human approval. The PDF requires review and approval.
- Follow-up messages.
- Vector databases, RAG, semantic cache or anything for large document sets. A search returns at most 50 posts, so everything fits in one prompt.
- Starting from seed accounts, and describing a segment in plain language. Both come later if time allows.
- An OpenAI provider. It gets added once the key arrives; the AI layer is built so that it's a small addition.
- A live test on real X. That waits for the developer account and credits.

## What would make this a failure

- A stranger gets messaged during our own testing.
- Anyone gets two messages.
- A message contains a claim about a person with no real post behind it.
- A secret ends up in git or in the submission zip.

## Approaches considered

| Approach | What it is | Verdict |
|---|---|---|
| Fully autonomous agent | AI finds, drafts and sends with nobody checking | Rejected. The PDF says drafts are "for us to review and approve", and messages go out from GenAI Fund's own account. |
| Keep the manual workbench | Today's app, plus the send switch | Rejected. Too slow for "at scale", and no real AI for an AI fund. |
| **AI does the work, human approves, app sends** | AI judges and drafts in a batch, a human works through a review queue, the app sends and tracks | **Chosen** by the user on 13 Nov. |

## The design

### 1. Who can be messaged (the send rule)

A new setting, `OUTREACH_POLICY`:

- `test_allowlist` (default): exactly today's behaviour. Only people in `TEST_RECIPIENT_IDS` with recorded consent can be messaged. This is what we use for our own testing.
- `operator_approved`: any discovered person can be messaged once a human approves the exact text. The allowlist and consent checks are skipped. Everything else still applies: do-not-contact list, the "already contacted" check, the pause switch, daily limit, budget, stale approval, evidence freshness.

In fake-data mode, `operator_approved` lets the fake people be "sent" to, so the whole flow can be demonstrated without X.

The Settings page and the top bar show which policy is active.

### 2. The AI layer

One small module that every AI feature goes through.

- Provider is chosen by the existing `DRAFT_PROVIDER` setting: `template` (no AI), `gemini`, or `anthropic`.
- **Gemini** is the tested provider. Settings: `GEMINI_API_KEY`, `GEMINI_MODEL` (default `gemini-flash-latest`), `GEMINI_FALLBACK_MODEL` (default `gemini-2.5-flash`).
- If the first model is busy or rate-limited, the call is tried once on the fallback model. If that fails too, the feature falls back to its non-AI behaviour and says so on screen.
- The existing Claude code path stays as it is, still untested and labelled so.
- AI is allowed in fake-data mode, because that data is synthetic.
- Only public profile text, public posts, the sender name and the stated purpose are sent to the model. DMs and tokens never are. Posts are passed as data, and the instructions tell the model to treat them as untrusted.
- Every call is recorded in a new `ai_calls` table: what it was for, provider, model, tokens in and out, time taken, outcome, error code.

Note for the write-up: Google's free tier may use submitted text to improve its products. What we send is public posts plus our own purpose line.

### 3. AI fit judging (rough filter first, careful judge second)

Discovery keeps its current first stage: one X search, keyword scoring, top 20 people.

New second stage: one AI call covering the top 10. For each person the AI returns:

- `fit`: strong, possible or weak
- `role`: builder, founder, researcher, other, or not a person (news and company accounts)
- `reason`: one or two sentences
- `quotes`: the exact post text the reason rests on

The app checks every quote appears word for word in that person's stored posts. If any quote fails, that person's AI judgment is thrown away and the keyword score stands alone. There is no confidence percentage anywhere, because models are poor at those.

Results are ordered by fit (strong, possible, unjudged, weak) and then keyword score. The card shows the AI reason and quotes alongside the existing point breakdown.

### 4. AI drafting, in a batch

- The results page gets a "Draft for top matches" button. It prepares a draft for every strong or possible person in that search, up to 10, skipping anyone already contacted, suppressed or already drafted.
- The draft prompt asks for a short, warm, specific message (under 500 characters) that refers to something the person actually posted, states who is writing and why, and ends with an opt-out line. It must list the quotes it relied on, and the existing quote check rejects anything invented.
- If the AI fails or cites something unsupported, the template draft is used and labelled as a fallback.
- The 10-drafts-per-login limit becomes a setting, `DRAFT_LIMIT_PER_SESSION`, default 40.

### 5. Review queue

A new page, **Review**, in the sidebar. It lists every draft waiting for a decision, best fit first. Each card shows:

```
Ada Tan  @ada_robotics          Fit: strong · researcher
Why: Building an open manipulation benchmark and releasing eval scripts.
  “I'm building an open robotics manipulation benchmark…”   (post, 13 Nov)
┌──────────────────────────────────────────────────────────┐
│ Hi Ada, saw your post about the manipulation benchmark…  │  (editable)
└──────────────────────────────────────────────────────────┘
[Approve and queue]  [Save edit]  [Skip]  [Do not contact]   AI draft · gemini
```

- **Approve and queue** approves that exact text and adds it to the send queue. If the text was edited, it must be saved first, as today.
- **Skip** removes the draft from the queue without blocking the person.
- If the person can't be messaged under the current policy, the card says why and the approve button is disabled.

The existing single-person page stays for detail, manual sending and the conversation view.

### 6. Paced send queue

- Approving in the queue marks the message as queued.
- A background worker inside the app wakes every 30 seconds. If sending is enabled, not paused, the sender is free, the gap since the last send is at least `SEND_MIN_GAP_SECONDS` (default 120) and the daily limit isn't reached, it sends the oldest queued message through the existing send function.
- Each queued message gets one stored request key, so a crash or restart can never send it twice.
- If X refuses (for example the person doesn't accept DMs from strangers), the message leaves the queue, is marked rejected with the reason, and shows under "Needs attention". The queue moves on.
- If the outcome is unknown, the queue stops, exactly as the existing rule demands, until a human checks.
- If X says "rate limited", the queue waits until the time X gives.
- `DAILY_SEND_LIMIT` default goes from 2 to 10.
- The Activity page shows queue position and the reason for any hold.

### 7. Reply checking

- Activity gets a "Sync all now" button.
- The same worker syncs each sent conversation every `AUTO_SYNC_MINUTES` (default 180; 0 turns it off). It stops checking a conversation 14 days after the send.
- X charges per DM event read, so the interval is deliberately long and counts against the existing X budget.

### 8. AI usage panel

Settings gets an "AI usage" section: number of calls, total tokens, average response time, failures, fallbacks, and a table of the last 20 calls.

### 9. Secrets

- `GEMINI_API_KEY` moves out of `.env.example` (tracked by git and included in the zip) into `.env` (ignored). `.env.example` keeps an empty placeholder.
- The packaging script also skips this `docs/superpowers` folder.

### 10. Database changes

- New table `ai_calls`.
- New columns: AI fit fields on `search_results`; queue fields on `outreach`.
- A second migration adds them to existing databases without touching data.

## Testing

- All existing tests keep passing.
- New tests: the send rule in both policies; the Gemini adapter against a mocked server, including the busy-model fallback; invented quotes rejected in judging and drafting; the queue's pacing, daily limit, crash-safety and stop-on-unknown; automatic sync.
- One real end-to-end run in fake-data mode with the real Gemini key, checked in a browser.
- Not tested until credentials arrive: anything on real X.

## My calls (correct any of these)

- Send defaults: 10 per day, 2 minutes apart.
- Reply check every 3 hours, stopping after 14 days.
- AI judges the top 10 per search; batch drafting covers up to 10.
- Drafts are capped at 500 characters when AI writes them.
- The Claude code stays in place, untested.
- Tests run against a throwaway local Postgres that I start myself; nothing touches your existing databases.
- This document is not committed until you ask.
