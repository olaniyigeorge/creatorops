"use client";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { ErrorBox, fmtDate, Loading, StatusBadge } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";

export default function Dashboard() {
  const { workspace, isOwner } = useWorkspace();
  const id = workspace.id;
  const onboarding = useAsync(() => api.onboarding(id), [id]);
  const approvals = useAsync(() => (isOwner ? api.approvals(id, "pending") : Promise.resolve([])), [id, isOwner]);
  const runs = useAsync(() => api.runs(id), [id]);
  const onboarded = !!onboarding.data;
  const pending = approvals.data?.length ?? 0;

  return (
    <>
      <h1>{workspace.name}</h1>
      <p className="muted">Autonomy: <strong>{workspace.autonomy}</strong></p>

      <div className="grid">
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Onboarding</h3>
          {onboarding.loading ? <Loading /> : onboarded ? (
            <p><span className="badge ok">complete</span> {onboarding.data?.channel_name}</p>
          ) : (
            <>
              <p><span className="badge warn">not started</span></p>
              <p className="muted small">Tell the agent about your channel before running strategy.</p>
            </>
          )}
          <Link className="btn" href={`/workspaces/${id}/onboarding`}>{onboarded ? "Edit answers" : "Start onboarding"}</Link>
        </div>

        {isOwner && (
          <div className={`card ${pending > 0 ? "warn" : ""}`}>
            <h3 style={{ marginTop: 0 }}>Pending approvals</h3>
            <p><strong style={{ fontSize: "1.6rem" }}>{approvals.loading ? "…" : pending}</strong></p>
            <Link className="btn" href={`/workspaces/${id}/approvals`}>Review</Link>
          </div>
        )}
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>How to test the flow</h3>
        <ol className="steps">
          <li>Complete <Link href={`/workspaces/${id}/onboarding`}>onboarding</Link>.</li>
          <li>Open <Link href={`/workspaces/${id}/runs`}>Runs</Link> and start <code>strategy_onboarding</code>.</li>
          <li>At Low/Medium autonomy it pauses: approve the niche, then the calendar, under <Link href={`/workspaces/${id}/approvals`}>Approvals</Link> (edits allowed).</li>
          <li>Open the <Link href={`/workspaces/${id}/calendar`}>Calendar</Link> and click “Generate creative” on an item.</li>
        </ol>
        <p className="muted small">Change autonomy in Settings: High skips approvals (except the first publishes).</p>
      </div>

      <h2>Latest runs</h2>
      <ErrorBox message={runs.error} />
      {runs.loading && <Loading />}
      {runs.data && runs.data.length === 0 && <p className="muted">No runs yet.</p>}
      {runs.data && runs.data.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Workflow</th><th>Status</th><th>Started</th></tr></thead>
            <tbody>
              {runs.data.slice(0, 5).map((r) => (
                <tr key={r.id}>
                  <td><Link href={`/workspaces/${id}/runs/${r.id}`}>{r.workflow}</Link></td>
                  <td><StatusBadge status={r.status} /></td>
                  <td>{fmtDate(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
