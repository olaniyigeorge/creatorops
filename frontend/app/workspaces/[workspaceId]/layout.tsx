"use client";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { ErrorBox, Loading } from "@/components/ui";
import { NotificationBell } from "@/components/notification-bell";
import { WorkspaceContext } from "@/components/workspace-context";

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const pathname = usePathname();
  const ws = useAsync(() => api.workspace(workspaceId), [workspaceId]);
  const list = useAsync(() => api.workspaces(), []);
  const role = list.data?.find((w) => w.id === workspaceId)?.role;

  if (ws.loading || list.loading) return <main className="container"><Loading what="Loading workspace" /></main>;
  if (ws.error || !ws.data || !role) {
    return (
      <main className="container">
        <ErrorBox message={ws.status === 404 ? "Workspace not found, or you are not a member." : (ws.error ?? "Could not load workspace")} />
        <Link href="/">Back to your workspaces</Link>
      </main>
    );
  }

  const base = `/workspaces/${workspaceId}`;
  const isOwner = role === "owner";
  const links = [
    { href: base, label: "Dashboard", exact: true },
    { href: `${base}/calendar`, label: "Calendar" },
    { href: `${base}/briefs`, label: "Briefs" },
    { href: `${base}/runs`, label: "Runs" },
    ...(isOwner ? [{ href: `${base}/approvals`, label: "Approvals" }] : []),
    { href: `${base}/members`, label: "Members" },
    { href: `${base}/onboarding`, label: "Onboarding" },
    { href: `${base}/settings`, label: "Settings" },
  ];

  return (
    <WorkspaceContext.Provider value={{ workspace: ws.data, role, isOwner, reload: ws.reload }}>
      <header className="topbar">
        <div className="topbar-inner">
          <Link href="/" className="brand">CreatorOps</Link>
          <strong title="Current workspace">{ws.data.name}</strong>
          <span className="badge">{role}</span>
          <nav className="nav" aria-label="Workspace">
            {links.map((l) => {
              const active = l.exact ? pathname === l.href : pathname.startsWith(l.href);
              return (
                <Link key={l.href} href={l.href} aria-current={active ? "page" : undefined}>{l.label}</Link>
              );
            })}
          </nav>
          <NotificationBell workspaceId={workspaceId} />
          <button onClick={async () => { await api.logout(); window.location.assign("/login"); }}>Sign out</button>
        </div>
      </header>
      <main className="container">{children}</main>
    </WorkspaceContext.Provider>
  );
}
