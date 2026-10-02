"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { EmptyState, ErrorBox, fmtDate, Loading, Notice, PageHeader, StatusBadge } from "@/components/ui";
import { Icon } from "@/components/icons";
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
      <PageHeader
        title="Runs"
        subtitle="Everything the agent has worked on."
        actions={isOwner && (
          <button className="primary" onClick={start} disabled={busy || !onboarded} title={onboarded ? "" : "Complete onboarding first"}>
            <Icon name="bolt" size={18} />{busy ? "Starting…" : "Run strategy"}
          </button>
        )}
      />
      {isOwner && !onboarding.loading && !onboarded && (
        <Notice icon="sparkle" tone="warn">Complete <Link href={`/workspaces/${id}/onboarding`}>onboarding</Link> before running the strategy workflow.</Notice>
      )}
      <ErrorBox message={error ?? runs.error} />
      {runs.loading && <Loading />}
      {runs.data && runs.data.length === 0 && <EmptyState icon="bolt" title="No runs yet">Runs appear here as soon as the agent starts working.</EmptyState>}
      <div className="list stagger">
        {(runs.data ?? []).map((r) => (
          <Link key={r.id} href={`/workspaces/${id}/runs/${r.id}`} className="card list-item">
            <span className="grow">
              <span className="card-title">{r.workflow.replace(/_/g, " ")}</span>
              <span className="meta">Started {fmtDate(r.created_at)}{r.finished_at && <><span className="sep">·</span>Finished {fmtDate(r.finished_at)}</>}</span>
            </span>
            <StatusBadge status={r.status} />
            <Icon name="chevron" className="chev" size={18} />
          </Link>
        ))}
      </div>
    </>
  );
}
