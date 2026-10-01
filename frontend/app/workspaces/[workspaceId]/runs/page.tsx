"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { ErrorBox, fmtDate, Loading, StatusBadge } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";

export default function RunsPage() {
  const router = useRouter();
  const { workspace, isOwner } = useWorkspace();
  const id = workspace.id;
  const runs = useAsync(() => api.runs(id), [id], {
    everyMs: 4000,
    shouldPoll: (d) => !!d?.some((r) => r.status === "pending" || r.status === "running"),
  });
  const onboarding = useAsync(() => api.onboarding(id), [id]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  async function start() {
    setBusy(true);
    setError(undefined);
    try {
      const run = await api.startRun(id, "strategy_onboarding");
      router.push(`/workspaces/${id}/runs/${run.id}`);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  const onboarded = !!onboarding.data;
  return (
    <>
      <div className="row between">
        <h1>Runs</h1>
        {isOwner && (
          <button className="primary" onClick={start} disabled={busy || !onboarded} title={onboarded ? "" : "Complete onboarding first"}>
            Start strategy_onboarding
          </button>
        )}
      </div>
      {isOwner && !onboarding.loading && !onboarded && (
        <div className="notice">Complete <Link href={`/workspaces/${id}/onboarding`}>onboarding</Link> before running the strategy workflow.</div>
      )}
      <ErrorBox message={error ?? runs.error} />
      {runs.loading && <Loading />}
      {runs.data && runs.data.length === 0 && <p className="muted">No runs yet.</p>}
      {runs.data && runs.data.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Workflow</th><th>Status</th><th>Started</th><th>Finished</th></tr></thead>
            <tbody>
              {runs.data.map((r) => (
                <tr key={r.id}>
                  <td><Link href={`/workspaces/${id}/runs/${r.id}`}>{r.workflow}</Link></td>
                  <td><StatusBadge status={r.status} /></td>
                  <td>{fmtDate(r.created_at)}</td>
                  <td>{fmtDate(r.finished_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
