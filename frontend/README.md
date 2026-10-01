# CreatorOps frontend

Next.js (App Router, TypeScript), plain CSS, no UI dependencies. Deploys to Vercel.

## Run locally

```bash
cp .env.example .env.local     # BACKEND_URL, NEXT_PUBLIC_DEV_LOGIN
npm install
npm run dev                    # http://localhost:3000
```

The backend must be running on `BACKEND_URL` (default `http://localhost:8000`). `/api/*` is
rewritten to it so the backend's `SameSite=Lax` session cookie stays same-origin.

Backend settings that must match: `CLIENT_DOMAIN=http://localhost:3000` and
`GOOGLE_REDIRECT_URI=http://localhost:3000/api/auth/google/callback`.

## Logging in

- **Google:** `/login` → "Continue with Google".
- **Dev login:** with `NEXT_PUBLIC_DEV_LOGIN=true` the login page also shows an email-only form
  that calls the backend's dev-only `POST /auth/dev-login`. Local testing only; never enable in production.
  Use two different emails (in two browser profiles) to test owner vs editor and invitations.

## Testing the whole flow

1. Create a workspace, complete **Onboarding**.
2. **Runs** → start `strategy_onboarding`. At Low/Medium autonomy it pauses.
3. **Approvals** → review the niche (you may pick another option or edit the JSON), approve; then the calendar.
4. **Calendar** → "Generate creative" on an item (runs automatically at Medium, asks at Low).
5. **Settings** → change autonomy and repeat. **Members** → invite an editor, open the link as that user.

## Layout

`lib/api.ts` is the only place that calls the backend (typed, 401 → `/login`, FastAPI `detail` made readable).
Routes mirror the backend: `/workspaces/[workspaceId]/{onboarding,settings,members,runs,approvals,calendar}`;
notification links from the backend (`/workspaces/{id}/approvals/{id}`) resolve to real pages.

```bash
npm run typecheck && npm run build
```
