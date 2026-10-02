// Typed API client. Every call goes through /api (rewritten to the backend) with the session cookie.

export type Role = "owner" | "editor";
export type Autonomy = "low" | "medium" | "high";
export type RunStatus = "pending" | "running" | "waiting_approval" | "succeeded" | "failed";
export type JsonObject = Record<string, unknown>;

export interface User { id: string; email: string; name: string }
export interface WorkspaceSummary { id: string; name: string; role: Role }
export interface Workspace {
  id: string;
  name: string;
  autonomy: Autonomy;
  guardrail_threshold: number;
  publish_human_floor: number;
  video_gen_enabled: boolean;
  video_budget_usd: number;
  video_spent_usd: number;
  brand_json: JsonObject;
  rubric_json: JsonObject;
}
export type WorkspaceUpdate = Partial<Pick<Workspace,
  "name" | "autonomy" | "guardrail_threshold" | "publish_human_floor" |
  "video_gen_enabled" | "video_budget_usd" | "brand_json" | "rubric_json">>;

export interface Member { user_id: string; email: string; name: string; role: Role }
export interface Invitation { id: string; email: string; role: Role; expires_at: string; token: string }

export type Goal = "growth" | "monetization" | "engagement";
export interface ChannelProfile {
  channel_name: string;
  goal: Goal;
  audience: string;
  tone: string;
  brand_voice: string;
  niche_hint: string | null;
  banned_topics: string[];
  extra_rules: string[];
  competitors: string[];
  videos_per_week: number;
  region_code: string;
}

export interface Action {
  id: string;
  step_key: string;
  type: string;
  summary: string;
  status: string;
  verdict: string | null;
  gate_reason: string | null;
  guardrail_score: number | null;
  estimated_cost_usd: number | null;
  result_json: JsonObject | null;
  created_at: string;
}
export interface Run {
  id: string;
  workflow: string;
  params_json: JsonObject;
  status: RunStatus;
  error: string | null;
  created_at: string;
  finished_at: string | null;
}
export interface RunDetail extends Run { actions: Action[] }

export interface Approval {
  id: string;
  status: "pending" | "approved" | "rejected";
  decision_note: string | null;
  decided_at: string | null;
  created_at: string;
  action: Action;
  payload: JsonObject;
  guardrail_feedback: string | null;
}
export interface ApprovalDecision {
  decision: "approve" | "reject";
  note?: string;
  edited_payload?: JsonObject;
}

export interface Notification {
  id: string;
  kind: string;
  title: string;
  body: string;
  link: string | null;
  read_at: string | null;
  created_at: string;
}

export interface CreativePackage {
  titles: { title: string; angle: string }[];
  description: string;
  tags: string[];
  thumbnail_concepts: string[];
  video_plan: string[];
}
export interface CalendarItem {
  id: string;
  idea_json: {
    title?: string;
    hook?: string;
    keywords?: string[];
    format?: string;
    creative?: CreativePackage;
    thumbnail_asset_id?: string;
  };
  scheduled_for: string | null;
  status: string;
}

export type BriefStatus = "draft" | "assigned" | "in_progress" | "submitted" | "done";
export interface BriefBody {
  objective: string;
  outline: { heading: string; notes: string }[];
  shot_list: string[];
  references: string[];
  deliverables: string[];
  editor_notes: string;
}
export interface Brief {
  id: string;
  calendar_item_id: string;
  title: string;
  editor_id: string | null;
  due_at: string | null;
  status: BriefStatus;
  overdue: boolean;
  followup_count: number;
  body_json: BriefBody;
  submitted_at: string | null;
  created_at: string;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

/** FastAPI's `detail` is a string, or a list of validation errors. Make either readable. */
export function detailToString(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        if (d && typeof d === "object") {
          const e = d as { loc?: unknown[]; msg?: string };
          const where = (e.loc ?? []).filter((p) => p !== "body").join(".");
          return where ? `${where}: ${e.msg ?? "invalid"}` : (e.msg ?? "invalid");
        }
        return String(d);
      })
      .join("; ");
  }
  return detail ? JSON.stringify(detail) : "Request failed";
}

export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong";
}

interface Options { redirectOn401?: boolean }

async function request<T>(method: string, path: string, body?: unknown, opts: Options = {}): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    credentials: "include",
    cache: "no-store",
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 401 && opts.redirectOn401 !== false && typeof window !== "undefined") {
    if (!window.location.pathname.startsWith("/login")) {
      const next = window.location.pathname + window.location.search;
      window.location.assign(`/login?next=${encodeURIComponent(next)}`);
    }
    throw new ApiError(401, "Not signed in");
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = undefined;
  try { data = text ? JSON.parse(text) : undefined; } catch { /* non-JSON error body */ }
  if (!res.ok) {
    const detail = data && typeof data === "object" ? (data as { detail?: unknown }).detail : undefined;
    throw new ApiError(res.status, detail !== undefined ? detailToString(detail) : `${res.status} ${res.statusText}`);
  }
  return data as T;
}

const get = <T,>(p: string, o?: Options) => request<T>("GET", p, undefined, o);
const post = <T,>(p: string, b?: unknown, o?: Options) => request<T>("POST", p, b ?? {}, o);

export const api = {
  me: () => get<User>("/auth/me", { redirectOn401: false }),
  devLogin: (email: string, name?: string) =>
    post<void>("/auth/dev-login", { email, ...(name ? { name } : {}) }, { redirectOn401: false }),
  logout: () => post<void>("/auth/logout"),

  workspaces: () => get<WorkspaceSummary[]>("/workspaces"),
  createWorkspace: (name: string) => post<Workspace>("/workspaces", { name }),
  workspace: (id: string) => get<Workspace>(`/workspaces/${id}`),
  updateWorkspace: (id: string, patch: WorkspaceUpdate) => request<Workspace>("PATCH", `/workspaces/${id}`, patch),

  members: (id: string) => get<Member[]>(`/workspaces/${id}/members`),
  invite: (id: string, email: string) => post<Invitation>(`/workspaces/${id}/invitations`, { email }),
  acceptInvitation: (token: string) => post<WorkspaceSummary>("/invitations/accept", { token }),

  onboarding: (id: string) => get<ChannelProfile>(`/workspaces/${id}/onboarding`),
  saveOnboarding: (id: string, profile: ChannelProfile) =>
    request<ChannelProfile>("PUT", `/workspaces/${id}/onboarding`, profile),

  runs: (id: string) => get<Run[]>(`/workspaces/${id}/runs`),
  run: (id: string, runId: string) => get<RunDetail>(`/workspaces/${id}/runs/${runId}`),
  startRun: (id: string, workflow: string, params?: JsonObject) =>
    post<Run>(`/workspaces/${id}/runs`, params ? { workflow, params } : { workflow }),

  approvals: (id: string, status?: string) =>
    get<Approval[]>(`/workspaces/${id}/approvals${status ? `?status=${status}` : ""}`),
  approval: (id: string, approvalId: string) => get<Approval>(`/workspaces/${id}/approvals/${approvalId}`),
  decide: (id: string, approvalId: string, d: ApprovalDecision) =>
    post<Approval>(`/workspaces/${id}/approvals/${approvalId}/decision`, d),

  notifications: (id: string, unread = false) =>
    get<Notification[]>(`/workspaces/${id}/notifications${unread ? "?unread=true" : ""}`),
  markRead: (id: string, nid: string) => post<Notification>(`/workspaces/${id}/notifications/${nid}/read`),

  briefs: (id: string) => get<Brief[]>(`/workspaces/${id}/briefs`),
  brief: (id: string, briefId: string) => get<Brief>(`/workspaces/${id}/briefs/${briefId}`),
  setBriefStatus: (id: string, briefId: string, status: BriefStatus) =>
    post<Brief>(`/workspaces/${id}/briefs/${briefId}/status`, { status }),
  updateBrief: (id: string, briefId: string, patch: { editor_id?: string; due_at?: string }) =>
    request<Brief>("PATCH", `/workspaces/${id}/briefs/${briefId}`, patch),

  calendar: (id: string) => get<CalendarItem[]>(`/workspaces/${id}/calendar`),
};
