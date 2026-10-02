"use client";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { EmptyState, ErrorBox, fmtDay, Loading, PageHeader, StatusBadge } from "@/components/ui";
import { Icon } from "@/components/icons";
import { useWorkspace } from "@/components/workspace-context";

export default function BriefsPage() {
  const { workspace, isOwner } = useWorkspace();
  const id = workspace.id;
  const briefs = useAsync(() => api.briefs(id), [id]);
  return (
    <>
      <PageHeader
        title={isOwner ? "Briefs" : "My briefs"}
        subtitle={isOwner ? "Instructions handed to your editors." : "Work assigned to you."}
        actions={<button className="sm" onClick={briefs.reload}><Icon name="refresh" size={16} />Refresh</button>}
      />
      <ErrorBox message={briefs.error} />
      {briefs.loading && <Loading />}
      {briefs.data && briefs.data.length === 0 && (
        <EmptyState
          icon="film"
          title="No briefs yet"
          action={isOwner ? <Link className="btn primary" href={`/workspaces/${id}/calendar`}>Open calendar</Link> : undefined}
        >
          {isOwner ? "Create a brief from any calendar item and assign it to an editor." : "Nothing has been assigned to you yet."}
        </EmptyState>
      )}
      <div className="list stagger">
        {(briefs.data ?? []).map((b) => (
          <Link key={b.id} href={`/workspaces/${id}/briefs/${b.id}`} className="card">
            <div className="row between" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}>
              <span className="card-title clamp">{b.title || "Untitled"}</span>
              <StatusBadge status={b.status} />
            </div>
            <p className="muted small" style={{ margin: "6px 0 0", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{b.body_json.objective}</p>
            <div className="meta">
              <Icon name="clock" size={14} />
              <span className={b.overdue ? "bad" : ""}>Due {fmtDay(b.due_at)}</span>
              {b.overdue && <span className="badge bad plain">overdue</span>}
            </div>
          </Link>
        ))}
      </div>
    </>
  );
}
