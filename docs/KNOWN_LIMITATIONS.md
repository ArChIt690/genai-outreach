# Known limitations

## Live verification pending

No X OAuth credentials were configured in this workspace. No real X discovery, DM exchange or outreach campaign was performed. The implemented live adapters have contract tests; actual entitlements, encryption/account compatibility, and provider behavior remain unverified. Google Gemini was called for real, but only on synthetic fixture posts.

Docker Engine was not running on this machine. Native Windows Python/PostgreSQL execution and browser testing are verified. Docker files are provided; a full container build/start still needs verification.

## Product boundaries

Only one operator and one active sender are supported. No message is sent without a person approving its exact text. There are no automated follow-ups, attachments or encrypted Chat subsystem. Manually added test recipients are labeled honestly.

## Assisted outreach limits

- Under OUTREACH_POLICY=operator_approved the allowlist and consent checks are skipped, so the person approving is the only judge of who is contacted. This policy has never run against real X.
- The app proves that each AI quote appears in the person's posts. It cannot prove that the AI's one-line reason, or the draft's wording, describes those posts fairly. The reviewer must read them.
- The AI judges only the top 10 people by keyword score. Someone the keyword filter ranks low is never seen by the AI.
- People can be found only by topic search. Starting from seed accounts and describing a segment in plain language are not built.
- Batch drafting runs inside the web request. Ten Gemini drafts take about a minute, and the page waits.
- The send queue and reply checks run in a thread inside the one app process. Stopping the app stops them. Run one process: several would not double-send (one stored request key per message, one sender lock) but they are not designed for it.
- When X answers "rate limited", that message is marked rejected and needs a fresh approval. The rest of the queue waits until the time X gives.
- An unknown send outcome stops the whole queue until a person reconciles or freezes that contact.
- DAILY_SEND_LIMIT=10 and the 120-second gap are our own caution. The real DM limits of an X account and API tier were not verified.
- Replies are checked automatically every AUTO_SYNC_MINUTES for 14 days after a send. Later replies appear only after Sync all now. Each check costs X reads; see COSTS.md.
- Model availability changes. On 14 Nov 2026 gemini-flash-latest timed out or returned 503 on the free tier, so the defaults are gemini-2.5-flash then gemini-flash-lite-latest.
- The OpenAI provider (Responses API, JSON output) is tested only against a mocked server. Its request format follows OpenAI's public API reference, but it has never called the real API, so the first live call may need a fix. Reasoning tokens count against the output limit; the adapter asks for at least 8,192 output tokens and treats a cut-off answer as a failure.
- Rewrite replaces the text in the box, including unsaved edits. A failed rewrite leaves the saved draft unchanged.
- The Anthropic path is untested, including its API version header.

Recent discovery covers a seven-day sample. The score is a heuristic, not a probability or a verified professional qualification. Public location is unverified. A negative search result is not evidence that suitable people do not exist.

History checks cannot see beyond X's available thirty-day window. Known outgoing prior contact blocks another initial message. The retained installation ledger prevents duplicates through this app; it cannot prevent independent messages from X or another tool.

An uncertain send deliberately holds the sender. Positive, unique history evidence can release the hold. Otherwise freeze the contact and investigate; there is no force-resend override. This favors avoiding duplicate contact over availability.

## Data handling and model limits

Evidence revalidation runs at drafting/approval/send and through a maintenance command. It is not a continuous upstream deletion listener. The operator must run maintenance and promptly handle removal requests.

Local purge clears source and imported reply bodies; submitted outgoing payloads remain for audit/reconciliation. For a full local removal, pause sends, disconnect tokens, back up only what may lawfully be retained, remove the dedicated database using PostgreSQL administration, and delete any independent backups/recordings. This eliminates historical duplicate protection. Do not repurpose the old workspace as if it had never contacted anyone.

Model output is validated for schema, source IDs and quoted spans. It cannot prove semantic truth. The operator must review the resulting claims. The Gemini adapter is verified with a real key on synthetic posts; the Anthropic adapter and its spend estimates are not live-verified.

Generation caches the current valid saved draft by evidence/profile/purpose/provider/model key after revalidation; failed model fallbacks are not reused as successful model generations. There is no multi-result generation cache. Local budget reservations are conservative estimates, not provider-enforced billing caps.

## Delivery limits

The one-page write-up is supplied as approximately 500 words of Markdown. Its final exported page layout still needs checking in the candidate's chosen editor. The timed demo script and synthetic screenshots are supplied; an actual live 3 to 5 minute recording must be made by the candidate.

The native cached-wheel setup trial does not include external account provisioning or a cold Docker image download. No claim is made that these external prerequisites complete in under fifteen minutes.

The dependency set emits a Starlette test-client deprecation warning for HTTPX. Tests pass; a future library update may require migrating test tooling to HTTPX2. The current initial migration snapshots this version's metadata; future schema changes need explicit new Alembic revisions.
