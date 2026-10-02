"use client";
import { useState } from "react";
import { api, errorMessage, type Invitation } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { Avatar, CopyButton, ErrorBox, fmtDate, Loading, Notice, PageHeader } from "@/components/ui";
import { Icon } from "@/components/icons";
import { useWorkspace } from "@/components/workspace-context";

export default function MembersPage() {
  const { workspace, isOwner } = useWorkspace();
  const id = workspace.id;
  const members = useAsync(() => api.members(id), [id]);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [invite, setInvite] = useState<Invitation>();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    setInvite(undefined);
    try {
      setInvite(await api.invite(id, email.trim()));
      setEmail("");
      members.reload();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const link = invite ? `${window.location.origin}/accept?token=${invite.token}` : "";
  return (
    <>
      <PageHeader title="Members" subtitle="People who work on this channel with you." />
      <ErrorBox message={members.error} />
      {members.loading && <Loading rows={2} />}
      <div className="list stagger">
        {(members.data ?? []).map((m) => (
          <div key={m.user_id} className="card list-item">
            <Avatar name={m.name || m.email} size={42} />
            <span className="grow" style={{ display: "grid", minWidth: 0 }}>
              <strong style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{m.name || m.email}</strong>
              {m.name && <span className="muted small" style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{m.email}</span>}
            </span>
            <span className="badge plain">{m.role}</span>
          </div>
        ))}
      </div>

      {isOwner ? (
        <form className="card pad-lg" style={{ marginTop: 20 }} onSubmit={submit}>
          <h3>Invite an editor</h3>
          <p className="muted small">Editors receive briefs and see activity, but can&apos;t approve, start runs or change settings. There&apos;s no invitation email yet: share the link yourself.</p>
          <label htmlFor="invite-email">Email</label>
          <input id="invite-email" type="email" inputMode="email" autoComplete="off" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <ErrorBox message={error} />
          <button className="primary block" style={{ marginTop: 14 }} disabled={busy || !email}><Icon name="mail" size={18} />{busy ? "Creating…" : "Create invitation"}</button>
        </form>
      ) : (
        <Notice icon="shield">Only the owner can invite members.</Notice>
      )}

      {invite && (
        <div className="card warn pad-lg" style={{ marginTop: 14 }} role="status">
          <strong>Invitation for {invite.email}</strong>
          <p className="muted small">Shown once. Expires {fmtDate(invite.expires_at)}. The invitee must sign in with exactly this email.</p>
          <div className="token">{link}</div>
          <div className="row"><CopyButton text={link} label="Copy link" /><CopyButton text={invite.token} label="Copy token" /></div>
        </div>
      )}
    </>
  );
}
