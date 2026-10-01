"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { ErrorBox, fmtDate, Loading, StatusBadge } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";

export default function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const { workspace, isOwner } = useWorkspace();
  const id = workspace.id;
  // Poll every 2s while the run is still moving; a parked run (waiting_approval) is re-checked
  // by reload after the owner decides.
  const run = useAsync(() => api.run(id, runId), [id, runId], {
    everyMs: 2000,
    shouldPoll: (d) => !d || d.status === "pending" || d.status === "running",
  });
  const d = run.data;

  return (
    <>
      <p><Link href={`/workspaces/${id}/runs`}>← All runs</Link></p>
      <ErrorBox message={run.error} />
      {run.loading && <Loading />}
      {d && (
        <>
          <div className="row between">
            <h1>{d.workflow}</h1>
            <div className="row"><StatusBadge status={d.status} /><button onClick={run.reload}>Refresh</button></div>
          </div>
          <p className="muted small">Started {fmtDate(d.created_at)} · Finished {fmtDate(d.finished_at)}</p>
          {Object.keys(d.params_json).length > 0 && <pre>{JSON.stringify(d.params_json, null, 2)}</pre>}
          <ErrorBox message={d.error ?? undefined} />

          {d.status === "waiting_approval" && (
            <div className="notice">
              This run is paused waiting for a decision.{" "}
              {isOwner ? <Link href={`/workspaces/${id}/approvals`}>Go to approvals →</Link> : "The workspace owner has been notified."}
            </div>
          )}

          <h2>Steps</h2>
          {d.actions.length === 0 && <p className="muted">No steps recorded yet.</p>}
          {d.actions.map((a) => (
            <div key={a.id} className="card">
              <div className="row between">
                <strong>{a.summary}</strong>
                <StatusBadge status={a.status} />
              </div>
              <p className="muted small">
                {a.step_key} · {a.type}
                {a.verdict ? ` · gate: ${a.verdict}` : ""}
                {a.guardrail_score !== null ? ` · guardrail ${a.guardrail_score.toFixed(2)}` : ""}
                {a.estimated_cost_usd !== null ? ` · est. $${a.estimated_cost_usd.toFixed(2)}` : ""}
              </p>
              {a.gate_reason && <p className="small">Gate: {a.gate_reason}</p>}
              {a.result_json && (
                <details>
                  <summary>Result</summary>
                  <pre>{JSON.stringify(a.result_json, null, 2)}</pre>
                </details>
              )}
            </div>
          ))}
        </>
      )}
    </>
  );
}
