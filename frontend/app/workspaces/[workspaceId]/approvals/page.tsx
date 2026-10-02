"use client";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { EmptyState, ErrorBox, fmtDate, Loading, Notice, PageHeader, StatusBadge } from "@/components/ui";
import { Icon } from "@/components/icons";
import { useWorkspace } from "@/components/workspace-context";

const FILTERS = [["pending", "Pending"], ["approved", "Approved"], ["rejected", "Rejected"], ["all", "All"]] as const;

export default function ApprovalsPage() {
  const { workspace, isOwner } = useWorkspace();
  const id = workspace.id;
  const [filter, setFilter] = useState<string>("pending");
  const list = useAsync(() => (isOwner ? api.approvals(id, filter === "all" ? undefined : filter) : Promise.resolve([])), [id, isOwner, filter]);

  if (!isOwner) return <><PageHeader title="Approvals" /><Notice icon="shield">Only the workspace owner can review approvals.</Notice></>;
  return (
    <>
      <PageHeader
        title="Approvals"
        subtitle="Decisions the agent needs from you before it continues."
        actions={<button className="sm" onClick={list.reload}><Icon name="refresh" size={16} />Refresh</button>}
      />
      <div className="seg" role="group" aria-label="Filter" style={{ marginBottom: 16 }}>
        {FILTERS.map(([v, label]) => (
          <button key={v} aria-pressed={filter === v} onClick={() => setFilter(v)}>{label}</button>
        ))}
      </div>
      <ErrorBox message={list.error} />
      {list.loading && <Loading />}
      {list.data && list.data.length === 0 && (
        <EmptyState icon="checkCircle" title={filter === "pending" ? "All caught up" : `Nothing ${filter === "all" ? "here" : filter}`}>
          {filter === "pending" ? "When the agent needs a decision, it will appear here." : "Nothing matches this filter."}
        </EmptyState>
      )}
      <div className="list stagger">
        {(list.data ?? []).map((a) => (
          <Link key={a.id} href={`/workspaces/${id}/approvals/${a.id}`} className="card list-item">
            <span className="grow">
              <span className="card-title clamp">{a.action.summary}</span>
              <span className="meta">
                <span>{a.action.type.replace(/_/g, " ")}</span><span className="sep">·</span><span>{fmtDate(a.created_at)}</span>
              </span>
              {a.action.gate_reason && <span className="muted small" style={{ display: "block", marginTop: 4 }}>{a.action.gate_reason}</span>}
            </span>
            <StatusBadge status={a.status} />
            <Icon name="chevron" className="chev" size={18} />
          </Link>
        ))}
      </div>
    </>
  );
}
