# CreatorOps

An AI marketing-operations manager for YouTube channels. It researches the niche, plans the content calendar, writes titles, descriptions and thumbnails, coordinates editors, and learns from what the channel owner approves or rejects. The owner decides how much it may do alone: **Low** (approve everything), **Medium** (routine work proceeds, strategy, calendar, publishing and AI video need approval) or **High** (mostly autonomous). Every action passes through a guardrail check and the autonomy policy first.

Optional AI video generation (Veo) is in scope but off by default, admin-triggered below High autonomy, and capped by a per-workspace budget.

- Product proposal: [`docs/creatorops.md`](docs/creatorops.md)
- Architecture, decisions, status and the fixes log: [`docs/architecture.md`](docs/architecture.md)

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js (App Router, TypeScript), deployed on Vercel |
| Backend | FastAPI, SQLAlchemy, Alembic, deployed on Render |
| Jobs | Celery and Redis (API, worker, and a single beat instance) |
| Database | PostgreSQL (Supabase in production, your local Postgres in development) |
| Agents | LangChain with Pydantic structured output, model-agnostic (Gemini first) |
| Assets | Cloudinary |
| Email | Resend (system mail), Gmail via per-owner OAuth (editor mail, from M4) |

## Status

Phase 1 (MVP foundation) is in progress.

| Milestone | State |
|---|---|
| M1 Platform: auth, workspaces, roles, invitations, tenant isolation | backend and UI done |
| M2 Gate and approvals: autonomy policy, guardrails, escalation, notifications | backend and UI done |
| M3 Strategy and Creative engines | backend and UI done; **not yet run against a live LLM** |
| M4 Editor workflow and Communication Agent | briefs, assignment, deadline follow-ups and Editor view done; Gmail, Google Calendar sync and the inbound reply webhook not built |
| M5 Optional AI video | building blocks done (provider, budget, restart-safe jobs); executor not built |

## Quick start (local)

Requires Python 3.12, Node 20+, and a local Postgres.

```bash
# 1. Database: creates role "bellz" (if missing) and databases creatorops + creatorops_test
bash backend/scripts/setup_local_db.sh

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # set DATABASE_URL (your bellz password), GEMINI_API_KEY; keep DEV_LOGIN_ENABLED=true
alembic upgrade head
TASKS_EAGER=true uvicorn app.api.main:app --reload --port 8000   # jobs run inline: no Redis/worker needed

# 3. Frontend (another terminal)
cd frontend
cp .env.example .env.local
npm install && npm run dev    # http://localhost:3000
```

Then in the browser: **dev login** → create a workspace → **onboarding** → run `strategy_onboarding` → approve the niche, then the calendar → on the calendar page, **Generate creative** for an item.

The strategy and creative steps need a real `GEMINI_API_KEY`. `YOUTUBE_API_KEY` is optional: without it, strategy runs on the channel profile alone and says so.

## Tests

```bash
cd backend && pytest                                  # in-memory SQLite, ~15 s
TEST_DATABASE_URL=postgresql+psycopg://bellz:<pw>@localhost:5432/creatorops_test pytest   # real Postgres
cd frontend && npx tsc --noEmit && npx next build
```

The Postgres run **drops all tables**, so the database name must contain `test` (enforced). LLMs, YouTube, Imagen, Cloudinary and Resend are replaced by fakes in the suite.

## Safety properties worth knowing

- **Tenant isolation:** every tenant row is reached only through `WorkspaceRepo`, which filters and stamps `workspace_id` and rejects references to another workspace's rows. A test fails if a new tenant model lacks an isolation test. Non-members get 404.
- **Fail closed:** an unavailable guardrail judge escalates to a human, an unpriced video generation is blocked, and an action with real effect but no executor fails instead of reporting success.
- **Approvals are deliberate:** emails deep-link to the in-app page rather than carrying one-click approve links (mail scanners prefetch links). Admin edits are validated before they are accepted.
- **Untrusted text is data:** workspace memory, competitor titles and model output are delimited and defanged in prompts, with an instruction not to obey them.

## Deployment

Backend: Render blueprint in [`render.yaml`](render.yaml) (API, worker, one beat, Redis; migrations run as a pre-deploy command). Frontend: Vercel, with `/api` proxied to the backend so the session cookie stays same-origin. `docker-compose.yml` is for local development only and contains no database. Details and Supabase, Cloudinary and Google OAuth notes are in `docs/architecture.md` section 8.

## License

Proprietary. Copyright (c) 2026 Olaniyi George. All rights reserved; see [`LICENSE`](LICENSE). No permission is granted to use, copy, modify or distribute this software without a written agreement.
