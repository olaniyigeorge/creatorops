"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { api, errorMessage, type BriefStatus } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { ErrorBox, fmtDay, Loading, PageHeader, StatusBadge } from "@/components/ui";
import { Icon } from "@/components/icons";
import { useWorkspace } from "@/components/workspace-context";

const EDITOR_NEXT: Partial<Record<BriefStatus, { to: BriefStatus; label: string; primary?: boolean }[]>> = {
  assigned: [{ to: "in_progress", label: "Start work", primary: true }, { to: "submitted", label: "Mark delivered" }],
  in_progress: [{ to: "submitted", label: "Mark delivered", primary: true }],
};

function List({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <>
      <h3>{title}</h3>
      <ul className="plain-list">{items.map((s, i) => <li key={i}>{s}</li>)}</ul>
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
        <Link className="btn" href={`/workspaces/${id}/briefs`}>Back to briefs</Link>
      </>
    );
  }
  const b = brief.data;
  const body = b.body_json;
  const editors = (members.data ?? []).filter((m) => m.role === "editor");
  const open = b.status === "draft" || b.status === "assigned" || b.status === "in_progress";
  const editorActions = !isOwner ? (EDITOR_NEXT[b.status] ?? []) : [];

  return (
    <>
      <PageHeader
        back={{ href: `/workspaces/${id}/briefs`, label: "Briefs" }}
        title={b.title || "Brief"}
        subtitle={
          <span className="meta" style={{ marginTop: 0 }}>
            <StatusBadge status={b.status} />
            {b.overdue && <span className="badge bad plain">overdue</span>}
            <span>Due {fmtDay(b.due_at)}</span>
            {b.followup_count > 0 && <span>· {b.followup_count} follow-up{b.followup_count === 1 ? "" : "s"} sent</span>}
          </span>
        }
      />
      <ErrorBox message={error} />

      <div className="card pad-lg">
        <h3>Objective</h3>
        <p>{body.objective}</p>
        <h3>Outline</h3>
        <ol className="steps" style={{ marginTop: 10 }}>
          {body.outline.map((s, i) => <li key={i}><strong>{s.heading}</strong>{s.notes && <div className="muted">{s.notes}</div>}</li>)}
        </ol>
        <List title="Shot list" items={body.shot_list} />
        <List title="References" items={body.references} />
        <List title="Deliverables" items={body.deliverables} />
        {body.editor_notes && <><h3>Notes</h3><p>{body.editor_notes}</p></>}
      </div>

      {editorActions.length > 0 && (
        <div className="sticky-actions action-bar">
          {editorActions.map((n) => (
            <button key={n.to} className={n.primary ? "primary" : ""} disabled={busy} onClick={() => act(() => api.setBriefStatus(id, b.id, n.to))}>{n.label}</button>
          ))}
        </div>
      )}

      {isOwner && (
        <div className="card pad-lg" style={{ marginTop: 14 }}>
          <h3>Manage</h3>
          {b.status === "submitted" && (
            <button className="primary block" disabled={busy} onClick={() => act(() => api.setBriefStatus(id, b.id, "done"))}>
              <Icon name="check" size={18} />Accept delivery
            </button>
          )}
          {open && (
            <>
              <label htmlFor="editor">Editor</label>
              <select id="editor" value={b.editor_id ?? ""} disabled={busy} onChange={(e) => e.target.value && act(() => api.updateBrief(id, b.id, { editor_id: e.target.value }))}>
                <option value="">Unassigned</option>
                {editors.map((m) => <option key={m.user_id} value={m.user_id}>{m.name || m.email}</option>)}
              </select>
              <label htmlFor="due">New deadline</label>
              <div className="row" style={{ flexWrap: "nowrap" }}>
                <input id="due" type="date" value={due} onChange={(e) => setDue(e.target.value)} />
                <button disabled={busy || !due} onClick={() => act(async () => { await api.updateBrief(id, b.id, { due_at: new Date(`${due}T17:00:00Z`).toISOString() }); setDue(""); })}>Move</button>
              </div>
            </>
          )}
        </div>
      )}
    </>
  );
}
