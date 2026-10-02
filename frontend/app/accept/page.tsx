"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { ErrorBox, Loading } from "@/components/ui";
import { Logo } from "@/components/icons";

function Accept() {
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";
  // 401 here redirects to /login?next=/accept?token=... and returns after sign-in.
  const { data: me, loading, error } = useAsync(() => api.me().catch(async (e) => {
    const next = window.location.pathname + window.location.search;
    window.location.assign(`/login?next=${encodeURIComponent(next)}`);
    throw e;
  }), []);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string>();

  async function accept() {
    setBusy(true);
    setErr(undefined);
    try {
      const ws = await api.acceptInvitation(token);
      router.replace(`/workspaces/${ws.id}`);
    } catch (e) {
      setErr(errorMessage(e));
      setBusy(false);
    }
  }

  return (
    <main className="auth">
      <div className="auth-card">
        <div className="auth-logo"><Logo size={64} /></div>
        <h1>You&apos;re invited</h1>
        <p className="tag">Join a CreatorOps workspace as an editor.</p>
        <div className="auth-panel">
          {!token && <ErrorBox message="This link has no invitation token." />}
          {loading && <Loading rows={1} />}
          {error && !me && <p className="muted">Redirecting to sign in…</p>}
          {me && token && (
            <>
              <p style={{ marginTop: 0 }}>Signed in as <strong>{me.email}</strong>. The invitation must have been sent to this email.</p>
              <ErrorBox message={err} />
              <button className="primary block" onClick={accept} disabled={busy}>{busy ? "Joining…" : "Join workspace"}</button>
            </>
          )}
        </div>
      </div>
    </main>
  );
}

export default function AcceptPage() {
  return (
    <Suspense>
      <Accept />
    </Suspense>
  );
}
