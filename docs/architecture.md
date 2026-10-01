# CreatorOps Architecture & Implementation Plan

Merges the original **YTA** prototype (LangChain niche agent, YouTube API helpers, Veo video generation) into the **CreatorOps** product described in `docs/creatorops.md`: an AI marketing-operations manager for YouTube channels, with configurable autonomy.

## 1. Decisions

| Topic | Decision |
|---|---|
| Product shape | CreatorOps. The AI coordinates humans (Owner, Editors) and escalates by default; full automation is the High-autonomy mode. |
| Agent framework | **LangChain** agents and chains with **Pydantic** schemas for all inputs and outputs (`with_structured_output`). Workflows are our own small re-entrant runner on Celery and Postgres (section 2.2 and `app/workflows/context.py`); LangGraph is not used, because pausing for days on a human approval is simpler to make durable in our own tables. |
| Model agnostic | Agents get models only from `app/llm/factory.py` (`init_chat_model`). Provider and model are config (`LLM_PROVIDER`, `LLM_MODEL`). Gemini is the first and default adapter. |
| Video generation | **In scope, optional.** Pluggable `VideoProvider` contract, Gemini Veo as the first adapter. Off by default (`VIDEO_GEN_ENABLED`), gated by workspace setting and budget. |
| Escalation | Editors still receive briefs. When video gen is enabled, the agent can *propose* an AI video to the Owner, who triggers it. Below High autonomy, generation always needs an admin click. |
| Email | Resend for system email (approvals, reports) and inbound reply parsing. **Each Owner's own Gmail via OAuth** for mail that should come from the Owner (editor briefs and follow-ups), sent with the `gmail.send` scope only. |
| Database | **Supabase Postgres**, used as plain Postgres through SQLAlchemy and Alembic (not Supabase Auth or the client SDK). |
| Asset storage | **Cloudinary** (thumbnails, AI-generated and editor video). |
| Deployment | **Backend on Render** (API, Celery worker, Celery beat as separate services from one Docker image), **frontend on Vercel**, external managed Postgres, Redis on Render Key Value. Docker Compose is for local development only. See section 8. |
| Calendar | Google Calendar through the same Google OAuth grant. |
| Repo | Restructured in place on branch `archi` (history preserved with `git mv`). |

## 2. System overview

```
 Next.js PWA ──► FastAPI ──► PostgreSQL
 (onboard, approve,   │        ▲  workspaces, memory, runs, actions, approvals
  monitor)            ▼        │
              Celery + Redis ──┴─► Agent runtime ─► Integrations
              (schedules, polling,      │             YouTube Data/Analytics, Resend,
               retries, long runs)      │             Gmail, Google Calendar, object storage
                                        ▼
                         ┌──── Gate: guardrails + autonomy ────┐
                         │ every side effect passes through it │
                         └─────────────────────────────────────┘
                         LLM factory (any provider) · VideoProvider (any provider)
```

### 2.1 The six modules

| Module | Responsibility | Built from |
|---|---|---|
| Strategy Engine | niche and competitor research, content calendar proposal | `agents/niche.py` plus new agents; `integrations/youtube.py` |
| Creative Engine | titles, descriptions, thumbnails, metadata; **video-gen proposal** | new; `video/` |
| Project Management Agent | briefs, deadlines, editor workflow | new |
| Communication Agent | escalations, status reports, follow-ups (Resend, Gmail) | new |
| Publishing Agent | upload and scheduling via YouTube API | new |
| Analytics Agent | channel performance, insights fed back to Strategy | `schemas/states.py` (`PerformanceMetrics`, `AnalyticsInsight`) |

### 2.2 The gate (the core of the product)

Agents never perform side effects directly. They return a `ProposedAction`; the gate decides.

```
agent ─► ProposedAction ─► guardrails.rate()  ─► score
                                   │
                    autonomy.decide(action, WorkspacePolicy, score, retries_left)
                                   │
        ┌───────────┬──────────────┼───────────────┬────────────┐
     PROCEED      RETRY        ESCALATE         BLOCKED
   run action   regenerate     create Approval   feature off /
                with feedback  + email + in-app  over budget
                               pause run
```

Rules (implemented in `app/gate/autonomy.py`, covered by `tests/test_gate.py`):

- **Hard blocks first**, regardless of trust: video gen disabled, or estimated cost over the remaining workspace budget.
- Guardrail score below the workspace threshold: **RETRY** with feedback while retries remain, then **ESCALATE**.
- **Low** autonomy: everything escalates. **Medium**: routine actions proceed; strategy, calendar, publish and video-gen escalate. **High**: proceeds.
- **Publish floor:** the first N publishes per workspace (default 3) always escalate, even at High.
- **Video gen below High** always needs the admin to trigger it.
- Every Approval decision (approve, reject, edit, free-text guidance) is written to workspace memory, which is how the agent learns preferences.

### 2.3 Optional AI video flow

```
Creative Engine drafts video plan + scene prompts
   └─► ProposedAction(GENERATE_VIDEO, estimated_cost)  ──► gate
         ├─ BLOCKED (disabled/over budget): plan goes to the editor as a normal brief
         ├─ ESCALATE: Owner gets "Generate this with AI? ~$X" in app + email
         │      ├─ approve ► Celery: provider.submit → poll (backoff) → fetch → storage → Asset row
         │      └─ decline ► brief goes to editor (default path, unchanged)
         └─ PROCEED (High autonomy, within budget): same Celery job, Owner notified
```

The editor path is always the fallback, and AI video can also be attached to a brief as a reference or draft cut. `VideoProvider` is `submit` / `poll` / `fetch` so jobs survive restarts and never block a request. The provider job id is stored on the Run. Adding Sora or Runway means one new file plus `registry.register(...)`.

### 2.4 Multi-tenancy and memory

- Every tenant-owned row carries `workspace_id`; all queries go through one repository layer that requires it. Optionally add Postgres row-level security as a second guard.
- `MemoryItem(workspace_id, kind, text, embedding?, source_approval_id)` kinds: `brand_guideline`, `preference`, `decision`, `performance_insight`. Retrieval is always scoped to the workspace and injected into agent prompts.
- Users can belong to several workspaces with a role per workspace (`owner`, `editor`).

## 3. Data model (first cut)

```
User(id, email, name)                    Membership(user_id, workspace_id, role)
Workspace(id, name, brand_json, rubric_json, autonomy, guardrail_threshold,
          publish_human_floor, video_gen_enabled, video_budget_usd)
Channel(id, workspace_id, youtube_channel_id, oauth_token_ref)
Run(id, workspace_id, workflow, status, state_json, video_job_json?)
Action(id, run_id, type, summary, payload_json, estimated_cost_usd,
       guardrail_score, verdict, created_at)
Approval(id, action_id, status, decided_by, decision_note, decided_at)
CalendarItem(id, workspace_id, video_idea_json, scheduled_for, status)
Brief(id, workspace_id, calendar_item_id, editor_id, due_at, status, body_json)
Asset(id, workspace_id, kind, storage_url, source('ai'|'editor'), metadata_json)
MemoryItem(...)  Notification(...)  EmailThread(id, workspace_id, gmail_thread_id, ...)
```

## 4. Repository layout (current)

```
backend/
  app/
    core/         config.py (Settings), logging.py
    db/           base.py, models.py, repo.py (WorkspaceRepo), session.py
    auth/         security.py (sessions, invitation tokens), google.py
    api/          main.py, deps.py, schemas.py; routes: auth, workspaces, runs, approvals,
                  notifications, onboarding, calendar
    llm/          factory.py                 model-agnostic chat models
    memory/       service.py                 per-workspace recall + prompt context
    gate/         autonomy.py, guardrails.py
    agents/       strategy.py, creative.py   (pm, comms, publishing, analytics: later phases)
    workflows/    context.py (gate execution, re-entrant steps), strategy_flow.py, creative_flow.py
    tasks/        Celery app, runner.py (claim, run, park, resume), dispatch.py, email_tasks.py
    comms/        notify.py                  escalation notices
    integrations/ youtube.py (market signals), email.py (Resend), storage.py (Cloudinary)
    image/        base.py, gemini_imagen.py  thumbnails (optional, pluggable)
    video/        base.py, registry.py, gemini_veo.py   AI video (optional, pluggable)
    schemas/      profile.py, strategy.py (live); states.py (original prototype models, kept for Phase 2 analytics/publishing)
  migrations/     Alembic (3 revisions)
  scripts/        setup_local_db.sh
  tests/          unit + HTTP end-to-end; shared fixtures in conftest.py, fake chat models in fakes.py
frontend/         Next.js app (App Router, TypeScript); /api proxied to the backend
docs/             creatorops.md (proposal), architecture.md (this file)
docker-compose.yml  Redis, API, worker, beat (local only; no database, see section 10)
render.yaml         production blueprint (backend only)
```

## 5. Implementation plan

Phases match the proposal (note its second "Phase 3" is a typo for Phase 2).

### Milestone 0: Foundation (done in this restructure)
- [x] Repo restructure, pycache untracked, `.gitignore` updated, lean `backend/requirements.txt`
- [x] Settings, model-agnostic LLM factory (Gemini default)
- [x] Niche agent on structured output (also fixed a prototype bug where `llm_candidates` was not a field and was silently dropped); superseded by the Strategy agent in M3 and removed
- [x] `VideoProvider` contract, registry, Gemini Veo adapter
- [x] Autonomy gate (pure logic, tested), guardrail judge

### Phase 1: MVP (6-8 weeks)

**M1. Platform skeleton (week 1-2): backend DONE, frontend and Google verification pending**
- SQLAlchemy models and Alembic migrations for section 3; docker-compose with Postgres and Redis
- FastAPI app: auth (Google sign-in), memberships and roles, workspace CRUD, repository layer enforcing `workspace_id`
- Celery app and a `run_workflow` task that persists `Run` state
- Status:
  - [x] SQLAlchemy models, first Alembic migration (verified on real Postgres: upgrade, downgrade, upgrade, `alembic check` clean)
  - [x] `WorkspaceRepo`: the only path to tenant rows; stamps and filters `workspace_id`; rejects references to other tenants' rows; a test fails if a new tenant model has no isolation test
  - [x] Google sign-in (sign-in scopes only), signed httpOnly session cookie, OAuth state check
  - [x] Workspaces, roles (owner/editor), settings, members, hashed single-use expiring invitations
  - [x] Celery app and persisted `run_workflow` task
  - [x] `Dockerfile`, `docker-compose.yml` (local), `render.yaml`
  - [ ] Next.js app with `/api` rewrites to the backend (not started)
  - [ ] Google OAuth app verification (human task; start now, it takes weeks)
  - [ ] Invitation emails (M2: Resend); until then the owner receives the token in the API response
- *Done when:* an Owner signs in, creates a workspace, and invites an Editor; cross-workspace access is rejected by tests. (Backend half met; 51 tests on SQLite and on Postgres.)

Auth design notes: sessions are a signed JWT in an httpOnly, `SameSite=Lax` cookie, which is the CSRF defence and relies on the frontend proxying `/api` through Next.js so calls stay same-site. Non-members get 404, not 403, so workspace existence is not revealed. Only the owner can change settings; spend and publish counters are not client-settable.

Running tests: `pytest` uses in-memory SQLite; `TEST_DATABASE_URL=postgresql+psycopg://.../creatorops_test pytest` runs the same suite on Postgres. **The suite drops all tables**, so the database name must contain `test` (enforced; it aborts otherwise).

**M2. Gate and approvals end-to-end (week 2-3): backend DONE**
- Status:
  - [x] `WorkflowContext.propose(step_key, generate)`: guardrails (with retry feedback loop), autonomy decision, then execute, escalate or block. Keyed by `step_key`, so workflows are **re-entrant**: finished steps return stored results, approved steps execute, pending steps pause again, and `generate` (LLM spend) is never re-run once an action exists
  - [x] Escalation parks the run (`waiting_approval`); an approval re-enters it via Celery; a rejection re-enters it too, with the admin's note available to the workflow
  - [x] Approvals API (owner only): list, detail, approve (optionally **with edited payload**) or reject with a note. Concurrent decisions resolve to exactly one winner (409 for the other)
  - [x] Every decision is written to workspace memory (`decision` or, when a note is given, `preference`)
  - [x] In-app notifications (owners only, per user) and Resend emails through a Celery task with retry and backoff
  - [x] Runs API (start, list, detail with the action trail); counters feed back into the gate (publishes, video spend)
  - [x] Run claiming is atomic, so a redelivered task cannot execute a run twice, and a run stuck in `running` after a worker death is reclaimed after `RUN_STALE_MINUTES`
  - [ ] Resend sending domain (SPF/DKIM) and the inbound reply webhook (moved to M4, where replies are first needed)
  - [ ] Approval UI (with the Next.js app)
- Deviation from the proposal: emails **deep-link to the in-app approval page** instead of containing signed approve/reject links. Mail scanners prefetch links and would auto-approve, and approving a publish should be a deliberate, logged-in act.
- Safety properties are covered by tests that were mutation-checked (removing the pending guard, or making the guardrail fail open, makes a test fail). (The earlier known limit on concurrent video spend is fixed: spend is now reserved atomically before executing and released if the executor fails. See section 9.)
- *Done when:* the same action proceeds or escalates correctly for Low/Medium/High (met, in `tests/test_gate_flow.py`), and an approval resumes the workflow (met over HTTP in `tests/test_approvals_api.py`; the email-click half is replaced by the deep link).

**M3. Strategy and Creative engines (week 3-5): backend DONE, UI built, not yet tried with a live LLM**
- Status:
  - [x] Onboarding API (`PUT/GET /workspaces/{id}/onboarding`): channel, goal, audience, tone, banned topics, rules, up to 10 competitors, cadence, region. The answers become the brand profile **and the guardrail rubric**, so what the owner said about tone and forbidden topics is what every generated asset is judged against. Resubmitting keeps the niche the agent chose. (A structured form, not a conversational interview; an LLM follow-up interview can be layered on later.)
  - [x] Memory service: recall always scoped to one workspace, admin guidance (`preference`) first, size-capped. Injected into every prompt as delimited data with an instruction not to obey it; stored text is defanged so it cannot close or forge the delimiters
  - [x] Market signals (`integrations/youtube.py`): trending plus competitor recent uploads (about 3 API quota units per competitor). Channel references are parsed strictly (handle, URL or id; anything else is rejected, which also blocks parameter injection). One failing source never fails the rest; with no key the strategy still runs and the prompt says there is no market data
  - [x] Strategy agent and `strategy_onboarding` workflow: the model proposes 3-5 niches; **code** scores them against the owner's goal (growth, monetization, engagement weights), picks the default, and assigns calendar dates from the posting cadence (never from the model). Scores are labelled in the proposal as model estimates, not measurements. Two high-stakes steps (niche, then 30-day calendar); a rejection note is already in memory when the next attempt runs, so the model sees it; up to 3 attempts per step
  - [x] Admin edits are validated per action type **before** the approval is recorded (invalid niche pick, empty or over-long calendar, titles over 100 characters give a 422 and the approval stays decidable)
  - [x] Creative agent and `creative_for_item` workflow: titles, description, tags, thumbnail concepts, video plan. YouTube's limits are enforced in code (title 100 characters, description 5000 bytes, tag and total tag length, no angle brackets or tags), including on admin edits. Routine, so Medium autonomy proceeds if the guardrails pass
  - [x] Optional thumbnail image step behind `IMAGE_GEN_ENABLED`: `ImageProvider` interface, Imagen adapter, Cloudinary `AssetStore` (private, per-workspace folders)
  - [x] Calendar API, run params validated per workflow, and `role` on the workspace response
  - [ ] **Not yet exercised against live services:** Gemini (no key was available), the YouTube Data API, Imagen and Cloudinary. Their adapters are tested against fakes and the request shapes follow each SDK's documented API; expect to fix small mismatches on first live run
  - [ ] Score calibration: niche scores are LLM estimates grounded on supplied data. Replace with measured metrics (search volume, competitor view velocity) once there is real data to compare against
- *Done when:* onboarding yields a calendar and creatives that pass the guardrail, with approvals recorded. Met with fake models (`tests/test_strategy.py`, `tests/test_creative.py`); a live-model run is the remaining check.

**M4. Editor workflow and Communication Agent (week 5-7)**
- Brief generation, assignment, deadline tracking; Editor view in the PWA
- Communication Agent: status reports, deadline follow-ups, escalation emails; Gmail threads for editor conversations
- Google Calendar sync for the content calendar
- *Done when:* a calendar item becomes a brief, the editor is emailed, and overdue briefs trigger a follow-up.

**M5. Optional AI video (week 7-8)**
- Creative agent emits a video plan and scene prompts and proposes `GENERATE_VIDEO` with a cost estimate
- Celery job: submit, poll with backoff, fetch to Cloudinary (`resource_type=video`, chunked upload), `Asset` row. Already done: the Veo adapter rebuilds an operation from its stored id, so a restarted worker can resume; budget reservation is atomic; unpriced or unconfigured video generation is blocked; a side-effecting action with no executor fails loudly. Remaining: the `GENERATE_VIDEO` executor, persisting the job id on the Run, and the "Generate with AI?" step in the creative workflow
- Workspace settings: enable toggle and monthly budget; spend ledger; "Generate with AI?" approval card
- *Done when:* with the flag on, an Owner can approve a generation, the file lands in storage, and spend is deducted; with it off, nothing changes.

### Phase 2: Automation (5-6 weeks)
- YouTube OAuth per channel, with encrypted token storage and refresh; quota tracking
- Analytics Agent: pull metrics, produce insights, feed Strategy; performance reports by email
- Publishing Agent: upload, thumbnail, schedule via YouTube API behind the gate (publish floor applies)
- Celery beat: scheduled research, weekly reports, calendar refresh
- Second LLM provider adapter exercised in CI, to prove model-agnosticism

### Phase 3: Autonomy expansion (2-3 weeks)
- Learn thresholds and preferences from approval history; suggest raising autonomy when approval rate is high
- Cross-workflow optimization and end-to-end High-autonomy runs
- Cost and quality dashboards; evaluation set for guardrails

## 6. Cross-cutting concerns

- **Cost control:** per-workspace LLM and video budgets, logged per Action, with hard blocks in the gate. LangSmith tracing, tagged by workspace.
- **Security:** OAuth tokens encrypted at rest; signed, expiring links in emails; secrets only in environment variables.
- **Testing:** pure-logic units (gate), agents tested with injected fake models (as `NicheDiscoveryAgent(model=...)` allows), provider adapters tested against fake clients, workspace isolation tests on every repository method.
- **Observability:** every Run and Action is persisted, so the activity log in the PWA is a read of the database.

## 7. Open questions

1. ~~Postgres and asset storage~~ Decided: Supabase Postgres and Cloudinary (sections 8.5, 8.6).
2. Success-metric targets for plan approval rate (the proposal says "high" without a number).
3. Image generation provider for thumbnails (Gemini image model as first adapter?).
4. ~~Gmail mailbox~~ Decided: each Owner's own mailbox via OAuth (section 8.3).
5. Proposal edits: fix the Phase numbering, and update "Out of Scope" to remove AI video generation now that it is in scope as an optional feature.

## 8. Deployment

### 8.1 Topology

```
Vercel (Next.js PWA) ──HTTPS──► Render web service: FastAPI (uvicorn)
                                      │
                 Render worker: Celery ──┤──► Redis (Render Key Value)
                 Render worker: Celery beat (exactly 1 instance)
                                      │
                                      └──► Supabase Postgres
                                           Cloudinary for assets
```

- **One Docker image** (`backend/Dockerfile`), three Render services with different start commands: `uvicorn app.api.main:app`, `celery -A app.tasks:celery_app worker`, `celery -A app.tasks:celery_app beat`. Defined in a `render.yaml` blueprint.
- **Compose is local only:** `docker-compose.yml` runs Postgres, Redis, API, worker and frontend so a new developer is productive with one command. Render does not deploy a compose file as a unit, and running everything on one Render Docker host gives up Vercel's frontend hosting and previews for no real gain.
- **Beat must be a single instance** or scheduled jobs fire twice. Do not autoscale it.
- **Do not use Render's free tier for the worker:** spin-down kills in-flight Veo jobs and scheduled tasks. This is also why the Veo operation id must be persisted on the Run (M5) so a restarted worker can resume polling.
- **Cross-origin setup:** Vercel and Render are different origins. Either proxy API calls through Next.js rewrites (same-origin cookies, simplest) or configure CORS with `SameSite=None; Secure` cookies. Recommended: Next.js rewrites.
- **Environments:** `main` deploys to production; PRs get Vercel previews pointed at a staging backend. Migrations run as a Render pre-deploy command (`alembic upgrade head`).

### 8.2 Config
Secrets live in Render and Vercel environment settings, never in the repo. The backend needs everything in `core/config.py`; the frontend needs only the API base URL and the Google client id.

### 8.3 Google OAuth (per-owner Gmail, Calendar, YouTube)

One Google OAuth client, one consent flow per Owner, tokens stored encrypted per workspace.

| Capability | Scope | Notes |
|---|---|---|
| Sign-in | `openid email profile` | |
| Send as the Owner | `gmail.send` | Sensitive scope. Enough for briefs and follow-ups. |
| Calendar | `calendar.events` | Sensitive scope. |
| YouTube read and analytics | `youtube.readonly`, `yt-analytics.readonly` | Phase 2. |
| YouTube upload | `youtube.upload` | Phase 2. |

Decisions and caveats:
- **Do not request `gmail.readonly` or `gmail.modify`.** They are *restricted* scopes: production use needs a third-party security assessment, which is expensive and slow. Instead, send editor emails through the Owner's Gmail with a `Reply-To` of a Resend inbound address (for example `brief+<id>@reply.yourdomain.com`). Resend's inbound webhook feeds replies back to the Communication Agent, so threads work without reading the Owner's mailbox.
- **Google app verification** is required for sensitive scopes before real users can connect. While the app is in "Testing" it is limited to 100 listed test users and refresh tokens expire after 7 days. Start the verification (privacy policy, domain, demo video) during M1; it can take weeks.
- **Token handling:** store refresh tokens encrypted (for example Fernet, key in env), handle revocation, and surface a "reconnect Gmail" notification when a refresh fails. If Gmail is not connected, fall back to Resend from the system address.
- **Sending limits:** consumer Gmail caps daily sends, which is fine for brief traffic but not for bulk mail. System notifications stay on Resend.

### 8.4 Added to the implementation plan
- **M1:** `backend/Dockerfile`, `docker-compose.yml` (local), `render.yaml`, Next.js rewrites, begin Google OAuth app verification.
- **M2:** Resend sending domain (SPF, DKIM) and inbound reply webhook.
- **M4:** Gmail send-as-Owner via OAuth with Resend fallback; inbound replies via the Resend webhook.

### 8.5 Supabase Postgres
- **Connection strings:** Render services are long-running, so use the Supavisor **session-mode** pooler (port 5432) or the direct connection for the API and workers. The **transaction-mode** pooler (port 6543) breaks psycopg prepared statements; if it is ever needed, disable them (`prepare_threshold=None`). Run **Alembic migrations over a direct or session connection**, never the transaction pooler.
- **Pool sizing:** API plus worker plus beat each hold a SQLAlchemy pool; keep `pool_size` small so the total stays under the Supabase plan's connection limit.
- **Tenant isolation stays in our code.** The backend connects with a privileged role that bypasses RLS, so the repository layer's mandatory `workspace_id` filter is the real guard (tested on every method). Supabase's auto-generated REST API exposes tables by default; **disable it or enable RLS with no public policies** on all tables so nothing is reachable except through FastAPI.
- **SSL:** require it (`sslmode=require`) in `DATABASE_URL`.
- Not used: Supabase Auth, Storage and Realtime. Auth is Google OAuth handled by FastAPI. This keeps the app portable to any Postgres.

### 8.6 Cloudinary assets
- `integrations/storage.py` wraps the Cloudinary SDK behind a small `AssetStore` interface (`upload`, `url`, `delete`), so storage stays swappable like the LLM and video providers.
- **Layout:** one folder per workspace (`creatorops/{workspace_id}/{kind}/...`) and the `public_id` saved on the `Asset` row. Tag assets with `workspace_id` and `source` (`ai` or `editor`).
- **Video:** use `resource_type="video"`. Large files (AI video, editor cuts) must use chunked upload (`upload_large`). Check the plan's maximum file size and monthly transformation and storage credits before enabling AI video; Veo output and editor video are the biggest consumers.
- **Editor uploads:** use signed direct-to-Cloudinary uploads from the PWA so large files do not pass through the API; the backend only issues the signature and records the resulting `public_id`.
- **Access:** use `type="authenticated"` or signed delivery URLs for unpublished work (briefs, drafts). Only published or public thumbnails may use plain URLs.
- **Veo flow change (M5):** `provider.fetch` writes the file to a temp dir, then `AssetStore.upload` sends it to Cloudinary and the temp file is deleted. Workers on Render have ephemeral disks, so nothing is kept locally.

## 9. Fixes and hardening log

Each item was a recommended fix from earlier reviews or was found while building M3. All have tests.

| Fix | Why it mattered | Where |
|---|---|---|
| Video spend is **reserved atomically** (one conditional `UPDATE`) before the executor runs, and released if it fails | Two concurrent generations could both pass the budget check and overspend | `workflows/context.py`, `tests/test_gate_flow.py` |
| A video action with an **unknown cost is blocked** at every autonomy level | An unpriced generation was treated as free. `VIDEO_COST_PER_SECOND_USD` must be set to enable it | `gate/autonomy.py`, `video/gemini_veo.py` |
| Actions with real effect (publish, video) **must have an executor**; otherwise the step fails | A missing executor would have recorded "executed" when nothing happened | `workflows/context.py` |
| **Veo jobs survive restarts**: the operation is rebuilt from its stored name; submit without a name is an error | The in-memory operation map lost in-flight jobs on every worker restart | `video/gemini_veo.py`, `tests/test_veo_provider.py` |
| The gate's action record is **committed before any side effect** | An executor crash rolled back the record and made a retry re-run `generate` (extra LLM spend) | `workflows/context.py` |
| **Guardrail outage fails closed** (escalates, does not retry against a dead judge) | A down judge must never wave content through | `workflows/context.py` |
| Admin edits to a proposal are **validated per action type before** the approval is claimed | An invalid edit would otherwise fail the run after approval | `workflows/context.py`, `api/approval_routes.py` |
| Memory and market data are **injected as delimited data**, defanged, with an instruction not to obey them | Admin notes, competitor titles and model echoes are untrusted text in prompts | `memory/service.py`, `integrations/youtube.py` |
| **Channel references parsed strictly** | A crafted "handle" could inject extra query parameters into YouTube API calls | `integrations/youtube.py` |
| YouTube **content limits enforced in code**, tags stripped, brackets removed | Models ignore length limits often enough to produce rejected uploads | `agents/creative.py` |
| Calendar **dates assigned in code**, round-half-up spacing | Model-chosen dates are unreliable; banker's rounding made slots uneven | `agents/strategy.py` |
| **Post-login redirect** returns to the page you were on, same-site relative paths only | The callback dropped the destination; a naive version would be an open redirect | `api/auth_routes.py` |
| **Dev-login** exists for local testing, off by default, 404 in production, and the app refuses to boot in production with it on | Testing the full flow without a verified Google app | `api/auth_routes.py`, `core/config.py` |
| API timestamps normalised to **UTC** | Some backends return naive datetimes | `api/calendar_routes.py` |
| Session factory **cached** | A new sessionmaker was built on every call | `db/session.py` |
| Test suite **refuses to run on a database not named `*test*`** | It drops every table; a mistake destroyed a migration baseline once | `tests/conftest.py` |
| **Frontend proxies to `127.0.0.1`**, not `localhost` | Node may resolve `localhost` to IPv6 while uvicorn listens on IPv4, so every API call failed | `frontend/next.config.mjs` |
| Prototype leftovers removed: `templates/index.html`, `feedbacks.json`, the demo graph, `scratch/`, the old niche agent, `langgraph` dependency | Superseded by the new structure; all remain in git history | repo root, `backend/` |
| Proposal fixes: Phase numbering, AI video moved into scope as optional, publish-floor rule and a numeric approval-rate target added | The document contradicted the design | `docs/creatorops.md` |

## 10. Local development and testing

**Database.** Local development uses the Postgres on your machine, owned by role `bellz`; Docker no longer runs a database, and production uses Supabase.

```bash
bash backend/scripts/setup_local_db.sh      # idempotent; creates role bellz if missing, plus
                                            # databases creatorops and creatorops_test
cp backend/.env.example backend/.env        # set DATABASE_URL (bellz password), DEV_LOGIN_ENABLED=true, GEMINI_API_KEY
cd backend && alembic upgrade head
```

**Run it.**

```bash
# backend (TASKS_EAGER=true runs jobs inline, so no Redis or worker is needed locally)
cd backend && TASKS_EAGER=true uvicorn app.api.main:app --reload --port 8000
# frontend
cd frontend && cp .env.example .env.local && npm install && npm run dev      # http://localhost:3000
```

Log in with the dev-login form, complete onboarding, run `strategy_onboarding`, approve the niche and the calendar, then generate creative for a calendar item. With `docker compose up` instead, containers reach the host database through `host.docker.internal` (see the comments in `docker-compose.yml`).

**Tests.** `pytest` (SQLite in memory, about 15 s). `TEST_DATABASE_URL=postgresql+psycopg://bellz:<pw>@localhost:5432/creatorops_test pytest` runs the same suite on real Postgres; the database name must contain `test`. Migrations were checked on real Postgres (upgrade, downgrade, upgrade, `alembic check`, and an upgrade over pre-existing rows).
