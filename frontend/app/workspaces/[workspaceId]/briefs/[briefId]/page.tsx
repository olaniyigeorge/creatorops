"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { api, errorMessage, type BriefStatus } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { ErrorBox, fmtDate, Loading, StatusBadge } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";

const EDITOR_NEXT: Partial<Record<BriefStatus, { to: BriefStatus; label: string }[]>> = {
  assigned: [{ to: "in_progress", label: "Start work" }, { to: "submitted", label: "Mark delivered" }],
  in_progress: [{ to: "submitted", label: "Mark delivered" }],
};

function List({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <>
      <h3>{title}</h3>
      <ul>{items.map((s, i) => <li key={i}>{s}</li>)}</ul>
    </>
  );
}

export default function BriefPage() {
  const { briefId } = useParams<{ briefId: string }>();
  const { workspace, isOwner } = useWorkspace();
  const id = workspace.id;
  const brief = useAsync(() => api.brief(id, briefId), [id, briefId]);
  const members = useAsync(() => (isOwner ? api.members(id) : Promise.resolve([])), [id, isOwner]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [due, setDue] = useState("");

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(undefined);
    try {
      await fn();
      brief.reload();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  if (brief.loading) return <Loading />;
  if (brief.error || !brief.data) {
    return (
      <>
        <ErrorBox message={brief.status === 404 ? "Brief not found, or it is not assigned to you." : brief.error} />
        <Link href={`/workspaces/${id}/briefs`}>Back to briefs</Link>
      </>
    );
  }
  const b = brief.data;
  const body = b.body_json;
  const editors = (members.data ?? []).filter((m) => m.role === "editor");
  const open = b.status === "draft" || b.status === "assigned" || b.status === "in_progress";

  return (
    <>
      <p><Link href={`/workspaces/${id}/briefs`}>← Briefs</Link></p>
      <div className="row between">
        <h1>{b.title || "Brief"}</h1>
        <span className="row">{b.overdue && <span className="badge bad">overdue</span>}<StatusBadge status={b.status} /></span>
      </div>
      <p className="muted small">Due {fmtDate(b.due_at)}{b.followup_count > 0 ? ` · ${b.followup_count} follow-up(s) sent` : ""}</p>
      <ErrorBox message={error} />

      <div className="card">
        <h3>Objective</h3>
        <p>{body.objective}</p>
        <h3>Outline</h3>
        <ol>{body.outline.map((s, i) => <li key={i}><strong>{s.heading}</strong>{s.notes ? ` — ${s.notes}` : ""}</li>)}</ol>
        <List title="Shot list" items={body.shot_list} />
        <List title="References" items={body.references} />
        <List title="Deliverables" items={body.deliverables} />
        {body.editor_notes && <><h3>Notes</h3><p>{body.editor_notes}</p></>}
      </div>

      {!isOwner && (EDITOR_NEXT[b.status] ?? []).length > 0 && (
        <div className="row">
          {EDITOR_NEXT[b.status]!.map((n) => (
            <button key={n.to} disabled={busy} onClick={() => act(() => api.setBriefStatus(id, b.id, n.to))}>{n.label}</button>
          ))}
        </div>
      )}

      {isOwner && (
        <div className="card">
          <h3>Manage</h3>
          {b.status === "submitted" && (
            <p><button disabled={busy} onClick={() => act(() => api.setBriefStatus(id, b.id, "done"))}>Accept delivery</button></p>
          )}
          {open && (
            <>
              <div className="row">
                <label>Editor{" "}
                  <select value={b.editor_id ?? ""} disabled={busy} onChange={(e) => e.target.value && act(() => api.updateBrief(id, b.id, { editor_id: e.target.value }))}>
                    <option value="">Unassigned</option>
                    {editors.map((m) => <option key={m.user_id} value={m.user_id}>{m.name || m.email}</option>)}
                  </select>
                </label>
              </div>
              <div className="row">
                <label>New deadline{" "}
                  <input type="date" value={due} onChange={(e) => setDue(e.target.value)} />
                </label>
                <button disabled={busy || !due} onClick={() => act(async () => { await api.updateBrief(id, b.id, { due_at: new Date(`${due}T17:00:00Z`).toISOString() }); setDue(""); })}>Move deadline</button>
              </div>
            </>
          )}
        </div>
      )}
    </>
  );
}
