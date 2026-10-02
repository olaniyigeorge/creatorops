"use client";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { EmptyState, ErrorBox, fmtDate, Loading, StatusBadge } from "@/components/ui";
import { Icon } from "@/components/icons";
import { useWorkspace } from "@/components/workspace-context";

export default function Dashboard() {
  const { workspace, isOwner } = useWorkspace();
  const id = workspace.id;
  const onboarding = useAsync(() => api.onboarding(id), [id]);
  const approvals = useAsync(() => (isOwner ? api.approvals(id, "pending") : Promise.resolve([])), [id, isOwner]);
  const runs = useAsync(() => api.runs(id), [id]);
  const calendar = useAsync(() => api.calendar(id), [id]);
  const briefs = useAsync(() => api.briefs(id), [id]);
  const onboarded = !!onboarding.data;
  const pending = approvals.data?.length ?? 0;
  const base = `/workspaces/${id}`;

  // The one thing to do next, so the dashboard always answers "what now?".
  const next = !onboarded
    ? { icon: "sparkle" as const, title: "Tell the agent about your channel", text: "Your answers shape every strategy and become the guardrails it is checked against.", href: `${base}/onboarding`, cta: "Start onboarding", show: isOwner }
    : pending > 0
      ? { icon: "checkCircle" as const, title: `${pending} decision${pending === 1 ? "" : "s"} waiting for you`, text: "The agent paused and needs your approval to continue.", href: `${base}/approvals`, cta: "Review now", show: isOwner }
      : (calendar.data?.length ?? 0) === 0
        ? { icon: "bolt" as const, title: "Run your first strategy", text: "The agent researches your niche, then proposes a content calendar.", href: `${base}/runs`, cta: "Open runs", show: isOwner }
        : undefined;

  return (
    <div className="stack" style={{ gap: 18 }}>
      <section className="hero">
        <h1>{workspace.name}</h1>
        <p>{isOwner ? "Here's where your channel stands." : "Here's what's assigned to you."}</p>
        <span className="chip"><Icon name="shield" size={14} />Autonomy: {workspace.autonomy}</span>
      </section>

      {next?.show && (
        <Link href={next.href} className="card accent list-item next-card">
          <span className="empty-icon" style={{ margin: 0, width: 46, height: 46, flex: "none" }}><Icon name={next.icon} /></span>
          <span className="grow" style={{ display: "grid" }}>
            <strong>{next.title}</strong>
            <span className="muted small">{next.text}</span>
          </span>
          <span className="btn primary sm">{next.cta}</span>
        </Link>
      )}

      <div className="stats">
        {isOwner && (
          <Link href={`${base}/approvals`} className={`card stat ${pending > 0 ? "warn" : ""}`}>
            <div className="num">{approvals.loading ? "–" : pending}</div>
            <div className="lbl">Awaiting approval</div>
          </Link>
        )}
        <Link href={`${base}/calendar`} className="card stat">
          <div className="num">{calendar.loading ? "–" : (calendar.data?.length ?? 0)}</div>
          <div className="lbl">Planned videos</div>
        </Link>
        <Link href={`${base}/briefs`} className="card stat">
          <div className="num">{briefs.loading ? "–" : (briefs.data?.filter((b) => b.status !== "done").length ?? 0)}</div>
          <div className="lbl">Open briefs</div>
        </Link>
        <Link href={`${base}/onboarding`} className="card stat">
          <div className="num" style={{ fontSize: "1.25rem", paddingTop: 7, paddingBottom: 5 }}>{onboarding.loading ? "–" : onboarded ? "Done" : "To do"}</div>
          <div className="lbl">Onboarding</div>
        </Link>
      </div>

      <section>
        <div className="row between" style={{ marginBottom: 10 }}>
          <h2 style={{ margin: 0 }}>Latest runs</h2>
          <Link href={`${base}/runs`} className="small">See all</Link>
        </div>
        <ErrorBox message={runs.error} />
        {runs.loading && <Loading rows={2} />}
        {runs.data && runs.data.length === 0 && (
          <EmptyState icon="bolt" title="No runs yet">When the agent works on your channel, each run shows up here.</EmptyState>
        )}
        <div className="list stagger">
          {(runs.data ?? []).slice(0, 4).map((r) => (
            <Link key={r.id} href={`${base}/runs/${r.id}`} className="card list-item">
              <span className="grow" style={{ display: "grid" }}>
                <strong>{r.workflow.replace(/_/g, " ")}</strong>
                <span className="muted small">{fmtDate(r.created_at)}</span>
              </span>
              <StatusBadge status={r.status} />
              <Icon name="chevron" className="chev" size={18} />
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
