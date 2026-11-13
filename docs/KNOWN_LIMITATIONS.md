# Known limitations

## Live verification pending

No X OAuth credentials or model credentials were configured in this workspace. No real X discovery, DM exchange, paid model call, or outreach campaign was performed. The implemented live adapters have contract tests; actual entitlements, encryption/account compatibility, and provider behavior remain unverified.

Docker Engine was not running on this machine. Native Windows Python/PostgreSQL execution and browser testing are verified. Docker files are provided; a full container build/start still needs verification.

## Product boundaries

Only one operator, one active sender and configured test recipients are supported. No unrestricted campaign mode, automated follow-ups, attachments or encrypted Chat subsystem exists. Manually added test recipients are labeled honestly.

Recent discovery covers a seven-day sample. The score is a heuristic, not a probability or a verified professional qualification. Public location is unverified. A negative search result is not evidence that suitable people do not exist.

History checks cannot see beyond X's available thirty-day window. Known outgoing prior contact blocks another initial message. The retained installation ledger prevents duplicates through this app; it cannot prevent independent messages from X or another tool.

An uncertain send deliberately holds the sender. Positive, unique history evidence can release the hold. Otherwise freeze the contact and investigate; there is no force-resend override. This favors avoiding duplicate contact over availability.

## Data handling and model limits

Evidence revalidation runs at drafting/approval/send and through a maintenance command. It is not a continuous upstream deletion listener. The operator must run maintenance and promptly handle removal requests.

Local purge clears source and imported reply bodies; submitted outgoing payloads remain for audit/reconciliation. For a full local removal, pause sends, disconnect tokens, back up only what may lawfully be retained, remove the dedicated database using PostgreSQL administration, and delete any independent backups/recordings. This eliminates historical duplicate protection. Do not repurpose the old workspace as if it had never contacted anyone.

Optional model generation validates schema, source IDs and quoted spans. It cannot prove semantic truth. The operator must review the resulting claims. The optional model adapter and its spend estimates are not live-verified.

Generation caches the current valid saved draft by evidence/profile/purpose/provider/model key after revalidation; failed model fallbacks are not reused as successful model generations. There is no multi-result generation cache. Local budget reservations are conservative estimates, not provider-enforced billing caps.

## Delivery limits

The one-page write-up is supplied as approximately 500 words of Markdown. Its final exported page layout still needs checking in the candidate's chosen editor. The timed demo script and synthetic screenshots are supplied; an actual live 3 to 5 minute recording must be made by the candidate.

The native cached-wheel setup trial does not include external account provisioning or a cold Docker image download. No claim is made that these external prerequisites complete in under fifteen minutes.

The dependency set emits a Starlette test-client deprecation warning for HTTPX. Tests pass; a future library update may require migrating test tooling to HTTPX2. The current initial migration snapshots this version's metadata; future schema changes need explicit new Alembic revisions.
