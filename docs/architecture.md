# CreatorOps Architecture & Implementation Plan

Merges the original **YTA** prototype (LangGraph niche agent, YouTube API helpers, Veo video generation) into the **CreatorOps** product described in `docs/creatorops.md`: an AI marketing-operations manager for YouTube channels, with configurable autonomy.

## 1. Decisions

| Topic | Decision |
|---|---|
| Product shape | CreatorOps. The AI coordinates humans (Owner, Editors) and escalates by default; full automation is the High-autonomy mode. |
| Agent framework | **LangChain** agents and chains with **Pydantic** schemas for all inputs and outputs (`with_structured_output`). LangGraph is kept only where a multi-step workflow needs it. |
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

## 4. Repository layout (current state after this restructure)

```
backend/
  app/
    core/         config.py (Settings), logging.py
    db/           base.py, models.py, repo.py (WorkspaceRepo), session.py   [done]
    auth/         security.py (sessions, invitation tokens), google.py       [done]
    api/          main.py, deps.py, auth_routes.py, workspace_routes.py       [done]
    tasks/        Celery app, runner.py (persisted workflow runs)             [done]
  migrations/     Alembic (initial schema)                                    [done]
    llm/          factory.py              model-agnostic chat models  [done]
    video/        base.py, registry.py, gemini_veo.py                 [done]
    gate/         autonomy.py [done], guardrails.py [done]
    agents/       niche.py [ported]; strategy, creative, pm, comms, publishing, analytics [todo]
    integrations/ youtube.py [moved]; email.py, gmail.py, calendar.py, storage.py (Cloudinary) [todo]
    schemas/      states.py (original YTA models; split per module as they are used)
    workflows/    legacy_graph.py (original demo); lifecycle workflows [todo]
    prompts/      prompts.yaml
  tests/          test_gate.py, test_video_registry.py
  scratch/        original experiments (legacy_main.py, langchain/langgraph demos)
frontend/         Next.js PWA [todo]
docs/             creatorops.md (proposal), architecture.md (this file)
```

Known leftovers: `templates/index.html` and `feedbacks.json` at the repo root are from the prototype and unused by the new structure. Delete them once confirmed. The README still describes the old YTA and should be rewritten after Phase 1.

## 5. Implementation plan

Phases match the proposal (note its second "Phase 3" is a typo for Phase 2).

### Milestone 0: Foundation (done in this restructure)
- [x] Repo restructure, pycache untracked, `.gitignore` updated, lean `backend/requirements.txt`
- [x] Settings, model-agnostic LLM factory (Gemini default)
- [x] Niche agent on structured output (also fixes a prototype bug where `llm_candidates` was not a field and was silently dropped)
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

Running tests: `pytest` uses in-memory SQLite; `TEST_DATABASE_URL=postgresql+psycopg://... pytest` runs the same suite on Postgres.

**M2. Gate and approvals end-to-end (week 2-3)**
- `Action`/`Approval` persistence; `gate.execute(action)` wrapper that runs guardrails, decides, and either runs, retries, or creates an Approval and pauses the Run
- Resume-on-decision: approval API resumes the paused Run; decisions written to `MemoryItem`
- Notification service (in-app) and Resend emails with signed approve/reject links
- *Done when:* the same action proceeds or escalates correctly for Low/Medium/High, and an approval email click resumes the workflow.

**M3. Strategy and Creative engines (week 3-5)**
- Onboarding interview (brand, tone, goals, competitors) producing the workspace rubric and memory
- Strategy agent: niche (extend `niche.py` with real YouTube data scores), competitor research, 30-day calendar proposal
- Creative agent: titles, descriptions, metadata, thumbnail prompt with image generation behind a provider interface like video
- Memory retrieval injected into prompts
- *Done when:* onboarding yields a calendar and creatives that pass the guardrail, with approvals recorded.

**M4. Editor workflow and Communication Agent (week 5-7)**
- Brief generation, assignment, deadline tracking; Editor view in the PWA
- Communication Agent: status reports, deadline follow-ups, escalation emails; Gmail threads for editor conversations
- Google Calendar sync for the content calendar
- *Done when:* a calendar item becomes a brief, the editor is emailed, and overdue briefs trigger a follow-up.

**M5. Optional AI video (week 7-8)**
- Creative agent emits a video plan and scene prompts and proposes `GENERATE_VIDEO` with a cost estimate
- Celery job: submit, poll with backoff (port the backoff from the old `video_gen.py`), fetch to object storage, `Asset` row; persist the operation id on the Run (the Veo adapter currently keeps operations in memory, which must be fixed before production)
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
