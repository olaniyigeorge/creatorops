"use client";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { ErrorBox, fmtDate, Loading, StatusBadge } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";

export default function BriefsPage() {
  const { workspace, isOwner } = useWorkspace();
  const id = workspace.id;
  const briefs = useAsync(() => api.briefs(id), [id]);
  return (
    <>
      <div className="row between">
        <h1>{isOwner ? "Briefs" : "My briefs"}</h1>
        <button onClick={briefs.reload}>Refresh</button>
      </div>
      <ErrorBox message={briefs.error} />
      {briefs.loading && <Loading />}
      {briefs.data && briefs.data.length === 0 && (
        <p className="muted">
          {isOwner
            ? <>No briefs yet. Open the <Link href={`/workspaces/${id}/calendar`}>calendar</Link> and create one for an item.</>
            : "Nothing has been assigned to you yet."}
        </p>
      )}
      {(briefs.data ?? []).map((b) => (
        <div className="card" key={b.id}>
          <div className="row between">
            <Link href={`/workspaces/${id}/briefs/${b.id}`}><strong>{b.title || "Untitled"}</strong></Link>
            <span className="row">
              <span className={`muted small${b.overdue ? " bad" : ""}`}>Due {fmtDate(b.due_at)}</span>
              {b.overdue && <span className="badge bad">overdue</span>}
              <StatusBadge status={b.status} />
            </span>
          </div>
          <p className="muted small">{b.body_json.objective}</p>
        </div>
      ))}
    </>
  );
}
