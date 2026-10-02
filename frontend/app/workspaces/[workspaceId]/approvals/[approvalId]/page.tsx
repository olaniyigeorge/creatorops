"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { api, errorMessage, type Approval, type JsonObject } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { ErrorBox, fmtDate, Loading, Notice, PageHeader, StatusBadge } from "@/components/ui";
import { Icon } from "@/components/icons";
import { useWorkspace } from "@/components/workspace-context";

type Json = JsonObject;
const asObj = (v: unknown): Json => (v && typeof v === "object" && !Array.isArray(v) ? (v as Json) : {});
const asArr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const str = (v: unknown): string => (typeof v === "string" ? v : v === undefined || v === null ? "" : String(v));

function parse(text: string): { value?: Json; error?: string } {
  try {
    const v: unknown = JSON.parse(text);
    if (!v || typeof v !== "object" || Array.isArray(v)) return { error: "Payload must be a JSON object" };
    return { value: v as Json };
  } catch (e) {
    return { error: `Invalid JSON: ${errorMessage(e)}` };
  }
}

function NicheView({ payload, onSelect, editable }: { payload: Json; onSelect: (name: string) => void; editable: boolean }) {
  const options = asArr(payload.options).map(asObj);
  const selected = str(payload.selected);
  return (
    <>
      <p className="muted small">{str(payload.estimates_note)}</p>
      <div role="radiogroup" aria-label="Choose a niche">
        {options.map((o) => {
          const name = str(o.name);
          return (
            <label key={name} className="pick">
              <input type="radio" name="niche" disabled={!editable} checked={selected === name} onChange={() => onSelect(name)} />
              <span className="grow">
                <strong>{name}</strong>
                <span className="muted small" style={{ display: "block" }}>{asArr(o.keywords).map(str).join(", ")}</span>
                <span style={{ display: "block", marginTop: 6, fontSize: "0.92rem" }}>{str(o.rationale)}</span>
              </span>
              <span className="score">{typeof o.score === "number" ? o.score.toFixed(2) : "—"}</span>
            </label>
          );
        })}
      </div>
      {str(payload.evidence) && <details><summary>Market evidence used</summary><pre>{str(payload.evidence)}</pre></details>}
    </>
  );
}

function CalendarView({ payload }: { payload: Json }) {
  const items = asArr(payload.items).map(asObj);
  return (
    <>
      <p>Niche: <strong>{str(payload.niche)}</strong> · {items.length} videos</p>
      <ol className="steps">
        {items.map((i, n) => (
          <li key={n}><strong>{str(i.title)}</strong> <span className="muted small">{fmtDate(str(i.scheduled_for))} · {str(i.format)}</span><div className="muted small">{str(i.hook)}</div></li>
        ))}
      </ol>
    </>
  );
}

function CreativeView({ payload }: { payload: Json }) {
  if (str(payload.kind) === "thumbnail") return <p>Thumbnail prompt: <em>{str(payload.prompt)}</em></p>;
  const pkg = asObj(payload.package);
  return (
    <>
      <h3>Title options</h3>
      <ul className="plain-list">{asArr(pkg.titles).map(asObj).map((t, i) => <li key={i}><strong>{str(t.title)}</strong> <span className="muted small">{str(t.angle)}</span></li>)}</ul>
      <h3>Description</h3>
      <pre style={{ whiteSpace: "pre-wrap" }}>{str(pkg.description)}</pre>
      <h3>Tags</h3>
      <p className="small">{asArr(pkg.tags).map(str).join(", ") || "—"}</p>
    </>
  );
}

function Form({ approval, workspaceId, onDone }: { approval: Approval; workspaceId: string; onDone: () => void }) {
  const original = useMemo(() => JSON.stringify(approval.payload, null, 2), [approval.payload]);
  const [text, setText] = useState(original);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<"approve" | "reject">();
  const [error, setError] = useState<string>();
  useEffect(() => setText(original), [original]);

  const parsed = parse(text);
  const pending = approval.status === "pending";
  const edited = !!parsed.value && JSON.stringify(parsed.value) !== JSON.stringify(approval.payload);
  const type = approval.action.type;

  function select(name: string) {
    if (parsed.value) setText(JSON.stringify({ ...parsed.value, selected: name }, null, 2));
  }

  async function decide(decision: "approve" | "reject") {
    setError(undefined);
    if (decision === "approve" && edited && !parsed.value) return setError(parsed.error);
    setBusy(decision);
    try {
      await api.decide(workspaceId, approval.id, {
        decision,
        ...(note.trim() ? { note: note.trim() } : {}),
        // Only send edits that really differ: an unchanged payload must not be recorded as "edited".
        ...(decision === "approve" && edited && parsed.value ? { edited_payload: parsed.value } : {}),
      });
      onDone();
    } catch (e) {
      const status = (e as { status?: number }).status;
      setError(status === 409 ? "This approval was already decided (maybe from another tab). Reloading." : errorMessage(e));
      if (status === 409) onDone();
    } finally {
      setBusy(undefined);
    }
  }

  const view = parsed.value ?? approval.payload;
  return (
    <>
      <h2>Proposal</h2>
      {type === "set_strategy" && <NicheView payload={view} onSelect={select} editable={pending} />}
      {type === "set_calendar" && <CalendarView payload={view} />}
      {type === "generate_creative" && <CreativeView payload={view} />}

      <details open={!["set_strategy", "set_calendar", "generate_creative"].includes(type)}>
        <summary>Edit raw payload (JSON)</summary>
        <label htmlFor="payload" className="small">Changing this approves your version instead of the agent&apos;s. It is validated by the server.</label>
        <textarea id="payload" className="code" spellCheck={false} disabled={!pending} value={text} onChange={(e) => setText(e.target.value)} />
        {parsed.error && <div className="alert" role="alert">{parsed.error}</div>}
      </details>

      {pending ? (
        <>
          <label htmlFor="note">Note to the agent <span className="hint">(optional; saved as guidance it will remember)</span></label>
          <textarea id="note" maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
          <p className="field-help">Reject without a note and the agent only learns that it was declined. Add a note to say why.</p>
          <ErrorBox message={error} />
          <div className="sticky-actions action-bar">
            <button className="primary" disabled={!!busy || !!parsed.error} onClick={() => decide("approve")} style={{ flexGrow: 2 }}>
              <Icon name="check" size={18} />{busy === "approve" ? "Approving…" : edited ? "Approve with my edits" : "Approve"}
            </button>
            <button className="danger" disabled={!!busy} onClick={() => decide("reject")}>
              {busy === "reject" ? "Rejecting…" : "Reject"}
            </button>
          </div>
        </>
      ) : (
        <Notice icon="clock">
          <StatusBadge status={approval.status} /> <span className="muted">{fmtDate(approval.decided_at)}</span>
          {approval.decision_note && <p style={{ marginBottom: 0 }}>Note: {approval.decision_note}</p>}
        </Notice>
      )}
    </>
  );
}

export default function ApprovalDetailPage() {
  const { approvalId } = useParams<{ approvalId: string }>();
  const { workspace, isOwner } = useWorkspace();
  const id = workspace.id;
  const a = useAsync(() => (isOwner ? api.approval(id, approvalId) : Promise.reject(new Error("Owner only"))), [id, approvalId, isOwner]);

  if (!isOwner) return <Notice icon="shield">Only the workspace owner can review approvals.</Notice>;
  const d = a.data;
  return (
    <>
      {!d && <Link className="back" href={`/workspaces/${id}/approvals`}><Icon name="back" size={16} />All approvals</Link>}
      <ErrorBox message={a.error} />
      {a.loading && <Loading />}
      {d && (
        <>
          <PageHeader
            back={{ href: `/workspaces/${id}/approvals`, label: "All approvals" }}
            title={d.action.summary}
            subtitle={<StatusBadge status={d.status} />}
          />
          <div className="card">
            <h3>Why you&apos;re being asked</h3>
            <p style={{ marginBottom: 6 }}>{d.action.gate_reason ?? "—"}</p>
            <div className="meta">
              <span>{d.action.type.replace(/_/g, " ")}</span>
              <span className="sep">·</span>
              <span>guardrail {d.action.guardrail_score !== null ? d.action.guardrail_score.toFixed(2) : "n/a"}</span>
              {d.action.estimated_cost_usd !== null && <><span className="sep">·</span><span>est. ${d.action.estimated_cost_usd.toFixed(2)}</span></>}
              <span className="sep">·</span><Link href={`/workspaces/${id}/runs`}>runs</Link>
            </div>
            {d.guardrail_feedback && <p className="small" style={{ marginBottom: 0 }}>Guardrail feedback: {d.guardrail_feedback}</p>}
          </div>
          <Form approval={d} workspaceId={id} onDone={a.reload} />
        </>
      )}
    </>
  );
}
