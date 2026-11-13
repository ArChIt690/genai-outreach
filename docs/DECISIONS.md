# Decisions

- Use FastAPI and server-rendered Jinja rather than a separate frontend build.
- PostgreSQL is mandatory: concurrency tests must exercise actual locks.
- Separate databases enforce immutable fixture/live mode.
- Live access is blocked until user-provided environment configuration and OAuth connection exist.
- No automatic send retries. Unknown outcomes retain a sender hold.
- Template drafting works without model credentials; optional model enhancement stays subordinate to the core workflow.
- UI direction: an analyst's evidence workbench, with blue-gray navigation, white document surfaces, indigo actions and amber caution. Palette: #172c45, #f2f5f9, #ffffff, #3656d4, #98651d, #286653. Segoe UI/system sans for controls; Georgia for the large page title only. Left-aligned split evidence/composition layout, with a compact table for activity. Avoid decorative metrics and identical dashboard cards. Prioritize source inspection and exact-text approval.
- Review of the design: replace generic KPI cards with a persistent workflow/status rail and evidence annotations, appropriate to an assessment tool that must show why an action is allowed.
