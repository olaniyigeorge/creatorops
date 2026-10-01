"use client";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { ErrorBox, fmtDate, Loading, StatusBadge } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";

export default function ApprovalsPage() {
  const { workspace, isOwner } = useWorkspace();
  const id = workspace.id;
  const [filter, setFilter] = useState("pending");
  const list = useAsync(() => (isOwner ? api.approvals(id, filter === "all" ? undefined : filter) : Promise.resolve([])), [id, isOwner, filter]);

  if (!isOwner) return <><h1>Approvals</h1><div className="notice">Only the workspace owner can review approvals.</div></>;
  return (
    <>
      <div className="row between">
        <h1>Approvals</h1>
        <div className="row">
          <label htmlFor="filter" className="small" style={{ margin: 0 }}>Show</label>
          <select id="filter" style={{ width: "auto" }} value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="all">All</option>
          </select>
          <button onClick={list.reload}>Refresh</button>
        </div>
      </div>
      <ErrorBox message={list.error} />
      {list.loading && <Loading />}
      {list.data && list.data.length === 0 && <p className="muted">Nothing {filter === "all" ? "here" : filter}.</p>}
      {(list.data ?? []).map((a) => (
        <Link key={a.id} href={`/workspaces/${id}/approvals/${a.id}`} className="card" style={{ display: "block", color: "inherit" }}>
          <div className="row between">
            <strong>{a.action.summary}</strong>
            <StatusBadge status={a.status} />
          </div>
          <p className="muted small" style={{ marginBottom: 0 }}>{a.action.type} · asked {fmtDate(a.created_at)}{a.action.gate_reason ? ` · ${a.action.gate_reason}` : ""}</p>
        </Link>
      ))}
    </>
  );
}
