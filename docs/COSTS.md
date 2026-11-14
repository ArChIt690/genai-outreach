# Costs and limits

No X API credits or paid hosting were purchased or used. Development ran locally with synthetic X data. The only external service called was Google Gemini on its free tier, at no charge.

The default local X allowance is USD 5 and the optional model allowance is USD 1. Search is capped at 50 posts/20 people, and DM pagination at ten pages of twenty events. Ten dispatch attempts per UTC day, a 120-second gap between queued sends and one outstanding sender attempt are deliberate limits of this app, not X platform quotas.

The application reserves worst-case estimated read costs, settles returned resource counts, and retains a conservative reservation if a call fails ambiguously. Author expansions and conversation pages are included. Concurrent reservations use PostgreSQL locks. Repeated reads may be overestimated because provider deduplication/discounts are deliberately not assumed.

The X pricing page reviewed on 2026-11-12 lists USD 0.005/post read, USD 0.010/user read, USD 0.010/DM event read and USD 0.015/DM creation. Example: 50 posts, 20 users, two created DMs and ten DM events total USD 0.58 before other calls, models and hosting. Verify the current developer-console prices before running.

Source: https://docs.x.com/x-api/getting-started/pricing

## Expected cost of running outreach

At the X prices listed above, per search: up to 50 posts and 20 users read, USD 0.45.

Per approved message: the quoted posts are re-read at approval and again at send (up to 3 posts each time, USD 0.03), the conversation history is read before sending (USD 0.01 per event returned, nothing for an empty history), and the DM itself is USD 0.015. About USD 0.05 per message.

Reply checks are the largest recurring cost. Each check re-reads the conversation, at USD 0.01 per event returned. A conversation holding only our one message costs USD 0.01 per check. At the default AUTO_SYNC_MINUTES=180 that is 8 checks a day for 14 days, about USD 1.12 per conversation. Set AUTO_SYNC_MINUTES=720 for about USD 0.28, or 0 and use Sync all now by hand. Every read is reserved against X_BUDGET_USD first, so the cap stops spending when it is reached.

Example day at the defaults: one search and 10 messages cost about USD 0.95 on the day, plus up to USD 11.20 of reply checks spread over the following 14 days. These are estimates from list prices, not measured bills.

Gemini, measured on 14 Nov 2026 with gemini-2.5-flash on three synthetic people: fit judging used about 930 tokens and took 8 seconds; each draft used about 520 tokens and took 5 to 6 seconds. A search plus ten drafts is roughly 6,000 tokens. That was free on the free tier. On a paid tier multiply by the current Gemini price. AI_DAILY_CALL_LIMIT caps calls per day.

OpenAI, from the prices on the account on 14 Nov 2026: gpt-6-luna is USD 0.10 per million input tokens and USD 0.50 per million output tokens; gpt-6.1-terra is USD 1.00 and USD 5.00. Using the token counts measured with Gemini (about 4,400 in and 1,600 out for a search plus ten drafts), that is about USD 0.0013 on luna or USD 0.013 on terra. Hidden reasoning tokens are billed as output and can multiply the output side several times; even at ten times, a search plus ten drafts stays under USD 0.01 on luna. One Rewrite on terra is about USD 0.001 to 0.01. These are calculations, not measured bills: the OpenAI adapter has not been run against the real API.

Template drafting adds no external model cost. The optional Anthropic adapter reserves USD 0.10/call rather than pretending to know arbitrary model pricing. This estimate may not cover every possible selected model/request: review its price and content size, and set provider-side spending controls before enablement. Reservations are not a billing guarantee.

Local fixture usage displayed in Settings is a synthetic accounting exercise. Do not report it as real expenditure.

Docker/hosting provider costs and candidate API entitlements remain installation-specific. No public deployment or recurring subscription is configured.
