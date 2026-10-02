"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { EmptyState, ErrorBox, fmtDate, Loading, Notice, PageHeader, StatusBadge } from "@/components/ui";
import { Icon } from "@/components/icons";
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
      {!d && <Link className="back" href={`/workspaces/${id}/runs`}><Icon name="back" size={16} />All runs</Link>}
      <ErrorBox message={run.error} />
      {run.loading && <Loading />}
      {d && (
        <>
          <PageHeader
            back={{ href: `/workspaces/${id}/runs`, label: "All runs" }}
            title={d.workflow.replace(/_/g, " ")}
            subtitle={<span className="meta" style={{ marginTop: 0 }}><StatusBadge status={d.status} /><span>Started {fmtDate(d.created_at)}</span>{d.finished_at && <span>· Finished {fmtDate(d.finished_at)}</span>}</span>}
            actions={<button className="sm" onClick={run.reload}><Icon name="refresh" size={16} />Refresh</button>}
          />
          {Object.keys(d.params_json).length > 0 && <pre>{JSON.stringify(d.params_json, null, 2)}</pre>}
          <ErrorBox message={d.error ?? undefined} />

          {d.status === "waiting_approval" && (
            <Notice icon="clock" tone="warn">
              This run is paused waiting for a decision.{" "}
              {isOwner ? <Link href={`/workspaces/${id}/approvals`} style={{ display: "inline-flex", alignItems: "center", gap: 2, fontWeight: 600 }}>Go to approvals<Icon name="chevron" size={16} /></Link> : "The workspace owner has been notified."}
            </Notice>
          )}

          <h2>Steps</h2>
          {d.actions.length === 0 && <EmptyState icon="clock" title="No steps yet">Steps show up here as the agent works.</EmptyState>}
          <div className="list stagger">
            {d.actions.map((a) => (
              <div key={a.id} className="card">
                <div className="row between" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}>
                  <strong style={{ lineHeight: 1.35 }}>{a.summary}</strong>
                  <StatusBadge status={a.status} />
                </div>
                <div className="meta">
                  <span>{a.step_key}</span><span className="sep">·</span><span>{a.type}</span>
                  {a.verdict && <><span className="sep">·</span><span>gate: {a.verdict}</span></>}
                  {a.guardrail_score !== null && <><span className="sep">·</span><span>guardrail {a.guardrail_score.toFixed(2)}</span></>}
                  {a.estimated_cost_usd !== null && <><span className="sep">·</span><span>est. ${a.estimated_cost_usd.toFixed(2)}</span></>}
                </div>
                {a.gate_reason && <p className="small" style={{ margin: "8px 0 0" }}>Gate: {a.gate_reason}</p>}
                {a.result_json && (
                  <details>
                    <summary>Result</summary>
                    <pre>{JSON.stringify(a.result_json, null, 2)}</pre>
                  </details>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}
