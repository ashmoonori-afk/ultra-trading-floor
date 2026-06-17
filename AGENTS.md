# AGENTS.md

## Scope

- This project is a separate paper-only dual-market trading bot. Do not edit or import code from `../Trading-agent-evolution-lab-review`; that repo remains a separate bot.
- Deliverables in this folder should be written in English. User-facing chat remains Korean per workspace-level guidance.

## Trading Safety

- Default and test modes are paper-only. Real broker APIs, credentials, live orders, websockets, and account access are out of scope until the user explicitly provides credentials and asks for live integration.
- Keep the live-order path fail-closed: no credentials plus no explicit opt-in means no order artifact and a nonzero CLI exit.
- Treat a 5% daily return as a paper validation target, not a guarantee or investment advice.

## Verification

- Use `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, and `uv run basedpyright`.
- Exercise the CLI surface after tests; unit tests alone are not enough.
