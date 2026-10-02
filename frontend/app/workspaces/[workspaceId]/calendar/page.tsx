"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, errorMessage, type CalendarItem, type Member } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { EmptyState, ErrorBox, Loading, PageHeader, StatusBadge } from "@/components/ui";
import { Icon } from "@/components/icons";
import { useWorkspace } from "@/components/workspace-context";

function DateTile({ iso }: { iso: string | null }) {
  const d = iso ? new Date(iso) : null;
  const ok = d && !Number.isNaN(d.getTime());
  return (
    <div style={{ width: 52, flex: "none", textAlign: "center", borderRadius: 14, padding: "6px 0", background: "var(--accent-soft)", color: "var(--accent)" }}>
      <div style={{ fontSize: "0.68rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em" }}>{ok ? d.toLocaleDateString(undefined, { month: "short" }) : "TBD"}</div>
      <div style={{ fontSize: "1.35rem", fontWeight: 800, lineHeight: 1.1 }}>{ok ? d.getDate() : "–"}</div>
    </div>
  );
}

function Item({ item, workspaceId, isOwner, editors }: { item: CalendarItem; workspaceId: string; isOwner: boolean; editors: Member[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [editorId, setEditorId] = useState("");
  const idea = item.idea_json;
  const creative = idea.creative;

  async function launch(workflow: string, params: Record<string, unknown>) {
    setBusy(true);
    setError(undefined);
    try {
      const run = await api.startRun(workspaceId, workflow, params);
      router.push(`/workspaces/${workspaceId}/runs/${run.id}`);
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  }

  return (
    <article className="card">
      <div className="list-item" style={{ alignItems: "flex-start" }}>
        <DateTile iso={item.scheduled_for} />
        <div className="grow">
          <div className="row between" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}>
            <strong style={{ lineHeight: 1.3 }}>{idea.title ?? "Untitled idea"}</strong>
            <StatusBadge status={item.status} />
          </div>
          <div className="meta">
            {idea.format && <span>{idea.format}</span>}
            {idea.keywords?.length ? <><span className="sep">·</span><span>{idea.keywords.slice(0, 3).join(", ")}</span></> : null}
          </div>
        </div>
      </div>
      {idea.hook && <p style={{ margin: "12px 0 4px" }}>{idea.hook}</p>}

      {creative && (
        <details>
          <summary>Creative · {creative.titles.length} title options</summary>
          <ul className="plain-list">{creative.titles.map((t, i) => <li key={i}><strong>{t.title}</strong> <span className="muted small">{t.angle}</span></li>)}</ul>
          <pre style={{ whiteSpace: "pre-wrap" }}>{creative.description}</pre>
          <p className="small">Tags: {creative.tags.join(", ") || "—"}</p>
          {creative.thumbnail_concepts.length > 0 && <p className="small">Thumbnail concepts: {creative.thumbnail_concepts.join(" | ")}</p>}
        </details>
      )}

      <ErrorBox message={error} />
      {isOwner && (
        <div className="stack" style={{ marginTop: 12 }}>
          <button className="sm" onClick={() => launch("creative_for_item", { calendar_item_id: item.id })} disabled={busy}>
            <Icon name="sparkle" size={16} />{creative ? "Regenerate creative" : "Generate creative"}
          </button>
          {item.status !== "briefed" && (
            <div className="row" style={{ flexWrap: "nowrap" }}>
              <select aria-label="Editor" value={editorId} onChange={(e) => setEditorId(e.target.value)} style={{ minHeight: 36, padding: "6px 36px 6px 12px" }}>
                <option value="">No editor yet (draft)</option>
                {editors.map((m) => <option key={m.user_id} value={m.user_id}>{m.name || m.email}</option>)}
              </select>
              <button className="sm" disabled={busy} onClick={() => launch("brief_for_item", { calendar_item_id: item.id, ...(editorId ? { editor_id: editorId } : {}) })}>
                <Icon name="film" size={16} />Brief
              </button>
            </div>
          )}
        </div>
      )}
    </article>
  );
}

export default function CalendarPage() {
  const { workspace, isOwner } = useWorkspace();
  const id = workspace.id;
  const cal = useAsync(() => api.calendar(id), [id]);
  const members = useAsync(() => api.members(id), [id]);
  const editors = (members.data ?? []).filter((m) => m.role === "editor");
  return (
    <>
      <PageHeader
        title="Content calendar"
        subtitle="What's planned, and what the agent has prepared for it."
        actions={<button className="sm" onClick={cal.reload}><Icon name="refresh" size={16} />Refresh</button>}
      />
      <ErrorBox message={cal.error} />
      {cal.loading && <Loading />}
      {cal.data && cal.data.length === 0 && (
        <EmptyState
          icon="calendar"
          title="Nothing planned yet"
          action={isOwner ? <Link className="btn primary" href={`/workspaces/${id}/runs`}>Run a strategy</Link> : undefined}
        >
          Run <code>strategy_onboarding</code> and approve the calendar to fill this in.
        </EmptyState>
      )}
      <div className="list stagger">
        {(cal.data ?? []).map((item) => <Item key={item.id} item={item} workspaceId={id} isOwner={isOwner} editors={editors} />)}
      </div>
    </>
  );
}
