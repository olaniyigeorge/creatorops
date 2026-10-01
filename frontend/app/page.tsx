"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { ErrorBox, Loading } from "@/components/ui";

export default function Home() {
  const router = useRouter();
  const { data: workspaces, error, loading, reload } = useAsync(() => api.workspaces(), []);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string>();

  // Google login always lands here, so honour a destination saved before the redirect.
  useEffect(() => {
    try {
      const next = sessionStorage.getItem("postLoginNext");
      if (next) {
        sessionStorage.removeItem("postLoginNext");
        router.replace(next);
      }
    } catch { /* storage unavailable */ }
  }, [router]);

  useEffect(() => {
    if (workspaces?.length === 1 && workspaces[0]) router.replace(`/workspaces/${workspaces[0].id}`);
  }, [workspaces, router]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFormError(undefined);
    try {
      const ws = await api.createWorkspace(name.trim());
      router.push(`/workspaces/${ws.id}`);
    } catch (err) {
      setFormError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <main className="container">
      <div className="row between">
        <h1>Your workspaces</h1>
        <button onClick={async () => { await api.logout(); window.location.assign("/login"); }}>Sign out</button>
      </div>
      <ErrorBox message={error} />
      {loading && <Loading />}
      {workspaces && workspaces.length === 0 && (
        <p className="muted">No workspaces yet. Create one to get started; each channel gets its own isolated workspace.</p>
      )}
      <div className="grid">
        {(workspaces ?? []).map((w) => (
          <Link key={w.id} href={`/workspaces/${w.id}`} className="card">
            <strong>{w.name}</strong>
            <div className="muted small">{w.role}</div>
          </Link>
        ))}
      </div>
      <form className="card" onSubmit={create}>
        <h2 style={{ marginTop: 0 }}>New workspace</h2>
        <label htmlFor="ws-name">Channel / workspace name</label>
        <input id="ws-name" type="text" required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />
        <ErrorBox message={formError} />
        <p><button className="primary" disabled={busy || !name.trim()}>Create workspace</button></p>
      </form>
      <button className="small" onClick={reload}>Refresh</button>
    </main>
  );
}
