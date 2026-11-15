# Decisions

Each line is a choice that was made and the reason for it.

## Product

- AI does the reading and writing; a person approves every message. The brief asks for drafts "for us to review and approve", and messages go out from the fund's own account. A fully autonomous sender was rejected for that reason.
- One setting, OUTREACH_POLICY, decides who can be messaged. The default, operator_approved, lets an approved message go to any discovered person, because the tool exists to run real outreach. test_allowlist allows only registered test accounts with recorded consent, so testing can never reach a stranger; the author's live test used it.
- Approval covers the exact text on screen. Editing, regenerating or rewriting a draft removes the approval and takes the message out of the send queue.
- No automatic send retries. An unknown outcome holds the sender and stops the queue until a person checks it. Avoiding a duplicate message matters more than availability.
- No automated follow-ups. The first message is the tool's job; the conversation continues in X.
- Seed accounts find people who do similar work, not people connected to the seed. This reuses the search and the AI judge, costs a few cents per seed, and avoids reading long following lists.

## AI

- Two-stage fit: a cheap keyword filter over the whole search, then one AI call over the top 10. This keeps cost and latency flat.
- Evidence instead of confidence. The model must quote the posts its judgment or draft rests on, and the app checks every quote word for word against stored posts. A failed check discards the output. There is no confidence percentage, because models are poor at them.
- Every AI feature has a non-AI fallback (keyword ranking, template draft) and says on screen when it was used.
- One module calls models. It tries a second model when the first is busy, caps calls per day, and records every call for the AI usage panel.
- OpenAI is the recommended provider: gpt-6-luna for everyday work, gpt-6.1-terra as backup and for rewrites the reviewer asks for. Gemini and Anthropic are alternatives behind the same interface.
- No vector database, RAG or semantic cache. A search returns at most 50 posts, which fit in one prompt.
- Posts and profiles are passed to the model as data, never as instructions, and the model has no tools. Search topics proposed by the model must pass the same character rules as typed topics.

## Engineering

- FastAPI with server-rendered Jinja pages; no separate frontend build.
- PostgreSQL is mandatory. Duplicate prevention relies on real row locks, and the concurrency tests exercise them.
- One process and one database. The send queue and reply checks run in a background thread inside the app, not in a separate worker or message broker. At 10 messages a day this is the simplest design that can be trusted.
- Each queued message stores a request key before anything is dispatched, so a crash or restart replays the stored result instead of sending again.
- Separate databases for fixture (synthetic) and live mode; the app refuses to start on a mismatch.
- Reply checks default to every 180 minutes because X bills each conversation read. See COSTS.md.
- Tests remove real credentials from the environment before they run, and the packaging script refuses to build while the settings template holds a secret.

## Interface

- An evidence workbench: blue-gray navigation, white document surfaces, indigo actions, amber caution. The main action on every screen is reading the evidence and deciding, not watching metrics.
- The Review page shows, per person: the AI's reason, the quotes behind it, the source posts, and the editable message, in that order.
