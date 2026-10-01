"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { ErrorBox, Loading } from "@/components/ui";

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
    <main className="narrow">
      <h1>Accept invitation</h1>
      {!token && <ErrorBox message="This link has no invitation token." />}
      {loading && <Loading />}
      {error && !me && <p className="muted">Redirecting to sign in…</p>}
      {me && token && (
        <>
          <p>Signed in as <strong>{me.email}</strong>. The invitation must have been sent to this email.</p>
          <ErrorBox message={err} />
          <button className="primary" onClick={accept} disabled={busy}>Join workspace</button>
        </>
      )}
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
