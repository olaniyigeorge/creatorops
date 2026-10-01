"use client";
import { useState } from "react";
import { api, errorMessage, type Invitation } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { CopyButton, ErrorBox, fmtDate, Loading } from "@/components/ui";
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
      <h1>Members</h1>
      <ErrorBox message={members.error} />
      {members.loading && <Loading />}
      {members.data && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Name</th><th>Email</th><th>Role</th></tr></thead>
            <tbody>
              {members.data.map((m) => (
                <tr key={m.user_id}><td>{m.name || "—"}</td><td>{m.email}</td><td><span className="badge">{m.role}</span></td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {isOwner ? (
        <form className="card" onSubmit={submit}>
          <h2 style={{ marginTop: 0 }}>Invite an editor</h2>
          <p className="muted small">Editors receive briefs and see activity, but cannot approve, start runs or change settings. There is no invitation email yet: share the link yourself.</p>
          <label htmlFor="invite-email">Email</label>
          <input id="invite-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <ErrorBox message={error} />
          <p><button className="primary" disabled={busy || !email}>Create invitation</button></p>
        </form>
      ) : (
        <div className="notice">Only the owner can invite members.</div>
      )}

      {invite && (
        <div className="card warn" role="status">
          <strong>Invitation for {invite.email}</strong>
          <p className="muted small">Shown once. Expires {fmtDate(invite.expires_at)}. The invitee must sign in with exactly this email.</p>
          <div className="token">{link}</div>
          <p className="row"><CopyButton text={link} label="Copy link" /><CopyButton text={invite.token} label="Copy token" /></p>
        </div>
      )}
    </>
  );
}
