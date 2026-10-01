"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, errorMessage, type CalendarItem } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { ErrorBox, fmtDate, Loading, StatusBadge } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";

function Item({ item, workspaceId, isOwner }: { item: CalendarItem; workspaceId: string; isOwner: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const idea = item.idea_json;
  const creative = idea.creative;

  async function generate() {
    setBusy(true);
    setError(undefined);
    try {
      const run = await api.startRun(workspaceId, "creative_for_item", { calendar_item_id: item.id });
      router.push(`/workspaces/${workspaceId}/runs/${run.id}`);
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <div className="row between">
        <strong>{idea.title ?? "Untitled idea"}</strong>
        <span className="row"><span className="muted small">{fmtDate(item.scheduled_for)}</span><StatusBadge status={item.status} /></span>
      </div>
      <p className="muted small">{idea.format}{idea.keywords?.length ? ` · ${idea.keywords.join(", ")}` : ""}</p>
      {idea.hook && <p>{idea.hook}</p>}
      {creative && (
        <details>
          <summary>Creative ({creative.titles.length} titles)</summary>
          <ul>{creative.titles.map((t, i) => <li key={i}><strong>{t.title}</strong> <span className="muted small">{t.angle}</span></li>)}</ul>
          <pre style={{ whiteSpace: "pre-wrap" }}>{creative.description}</pre>
          <p className="small">Tags: {creative.tags.join(", ") || "—"}</p>
          {creative.thumbnail_concepts.length > 0 && <p className="small">Thumbnail concepts: {creative.thumbnail_concepts.join(" | ")}</p>}
        </details>
      )}
      <ErrorBox message={error} />
      {isOwner && (
        <button onClick={generate} disabled={busy}>{creative ? "Regenerate creative" : "Generate creative"}</button>
      )}
    </div>
  );
}

export default function CalendarPage() {
  const { workspace, isOwner } = useWorkspace();
  const id = workspace.id;
  const cal = useAsync(() => api.calendar(id), [id]);
  return (
    <>
      <div className="row between"><h1>Content calendar</h1><button onClick={cal.reload}>Refresh</button></div>
      <ErrorBox message={cal.error} />
      {cal.loading && <Loading />}
      {cal.data && cal.data.length === 0 && (
        <p className="muted">Nothing planned yet. Run <code>strategy_onboarding</code> from <Link href={`/workspaces/${id}/runs`}>Runs</Link> and approve the calendar.</p>
      )}
      {(cal.data ?? []).map((item) => <Item key={item.id} item={item} workspaceId={id} isOwner={isOwner} />)}
    </>
  );
}
