"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { Avatar, EmptyState, ErrorBox, Loading } from "@/components/ui";
import { Icon, Logo } from "@/components/icons";
import { InstallPrompt } from "@/components/pwa";

export default function Home() {
  const router = useRouter();
  const { data: workspaces, error, loading } = useAsync(() => api.workspaces(), []);
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
    <main className="content" style={{ paddingBottom: 40 }}>
      <div className="row between" style={{ marginBottom: 22, paddingTop: "var(--safe-t)" }}>
        <span className="brand"><Logo size={32} />CreatorOps</span>
        <button className="ghost sm" onClick={async () => { await api.logout(); window.location.assign("/login"); }}>
          <Icon name="logout" size={16} />Sign out
        </button>
      </div>

      <div className="page-head">
        <h1>Your channels</h1>
        <p className="muted">Each channel gets its own isolated workspace.</p>
      </div>

      <ErrorBox message={error} />
      {loading && <Loading rows={2} />}
      {workspaces && workspaces.length === 0 && (
        <EmptyState icon="play" title="No workspaces yet">Create one below to start planning your channel.</EmptyState>
      )}
      <div className="list stagger">
        {(workspaces ?? []).map((w) => (
          <Link key={w.id} href={`/workspaces/${w.id}`} className="card list-item">
            <Avatar name={w.name} size={44} />
            <span className="grow" style={{ display: "grid" }}>
              <strong>{w.name}</strong>
              <span className="muted small" style={{ textTransform: "capitalize" }}>{w.role}</span>
            </span>
            <Icon name="chevron" className="chev" />
          </Link>
        ))}
      </div>

      <form className="card pad-lg accent" style={{ marginTop: 22 }} onSubmit={create}>
        <h3>New workspace</h3>
        <label htmlFor="ws-name" style={{ marginTop: 6 }}>Channel name</label>
        <input id="ws-name" type="text" required maxLength={200} placeholder="e.g. Tech with Tola" value={name} onChange={(e) => setName(e.target.value)} />
        <ErrorBox message={formError} />
        <button className="primary block" style={{ marginTop: 14 }} disabled={busy || !name.trim()}>
          <Icon name="plus" size={18} />{busy ? "Creating…" : "Create workspace"}
        </button>
      </form>
      <InstallPrompt />
    </main>
  );
}
