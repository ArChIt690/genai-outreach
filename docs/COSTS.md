# Costs and limits

No live API credits, model calls or paid hosting were purchased or used in this implementation run. Development ran locally with synthetic provider data.

The default local X allowance is USD 5 and the optional model allowance is USD 1. Search is capped at 50 posts/20 people, and DM pagination at ten pages of twenty events. Two dispatch attempts per UTC day and one outstanding sender attempt are deliberate test limits, not X platform quotas.

The application reserves worst-case estimated read costs, settles returned resource counts, and retains a conservative reservation if a call fails ambiguously. Author expansions and conversation pages are included. Concurrent reservations use PostgreSQL locks. Repeated reads may be overestimated because provider deduplication/discounts are deliberately not assumed.

The X pricing page reviewed on 2026-11-12 lists USD 0.005/post read, USD 0.010/user read, USD 0.010/DM event read and USD 0.015/DM creation. Example: 50 posts, 20 users, two created DMs and ten DM events total USD 0.58 before other calls, models and hosting. Verify the current developer-console prices before running.

Source: https://docs.x.com/x-api/getting-started/pricing

Template drafting adds no external model cost. The optional Anthropic adapter reserves USD 0.10/call rather than pretending to know arbitrary model pricing. This estimate may not cover every possible selected model/request: review its price and content size, and set provider-side spending controls before enablement. Reservations are not a billing guarantee.

Local fixture usage displayed in Settings is a synthetic accounting exercise. Do not report it as real expenditure.

Docker/hosting provider costs and candidate API entitlements remain installation-specific. No public deployment or recurring subscription is configured.
