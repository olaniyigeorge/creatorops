"use client";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { Avatar, ErrorBox, Loading } from "@/components/ui";
import { Icon, Logo, type IconName } from "@/components/icons";
import { BellButton, NotificationPanel, useNotifications } from "@/components/notification-bell";
import { InstallPrompt } from "@/components/pwa";
import { WorkspaceContext } from "@/components/workspace-context";

interface NavLink { href: string; label: string; icon: IconName; exact?: boolean; count?: number }

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const pathname = usePathname();
  const ws = useAsync(() => api.workspace(workspaceId), [workspaceId]);
  const list = useAsync(() => api.workspaces(), []);
  const role = list.data?.find((w) => w.id === workspaceId)?.role;
  const isOwner = role === "owner";
  const notes = useNotifications(workspaceId);
  const pending = useAsync(
    () => (isOwner ? api.approvals(workspaceId, "pending") : Promise.resolve([])),
    [workspaceId, isOwner],
    { everyMs: 30000, shouldPoll: () => isOwner },
  );
  const [more, setMore] = useState(false);
  const [bell, setBell] = useState(false);

  // Close overlays on navigation, lock page scroll while the sheet is open.
  useEffect(() => { setMore(false); setBell(false); }, [pathname]);
  useEffect(() => {
    document.body.style.overflow = more ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [more]);

  if (ws.loading || list.loading) {
    return <main className="content"><Loading what="Loading workspace" rows={4} /></main>;
  }
  if (ws.error || !ws.data || !role) {
    return (
      <main className="content">
        <ErrorBox message={ws.status === 404 ? "Workspace not found, or you are not a member." : (ws.error ?? "Could not load workspace")} />
        <Link className="btn" href="/">Back to your workspaces</Link>
      </main>
    );
  }

  const base = `/workspaces/${workspaceId}`;
  const approvalsCount = pending.data?.length ?? 0;
  const all: NavLink[] = [
    { href: base, label: "Home", icon: "home", exact: true },
    { href: `${base}/calendar`, label: "Calendar", icon: "calendar" },
    { href: `${base}/briefs`, label: "Briefs", icon: "film" },
    ...(isOwner ? [{ href: `${base}/approvals`, label: "Approvals", icon: "checkCircle" as IconName, count: approvalsCount }] : []),
    { href: `${base}/runs`, label: "Runs", icon: "bolt" },
    { href: `${base}/members`, label: "Members", icon: "users" },
    { href: `${base}/onboarding`, label: "Onboarding", icon: "sparkle" },
    { href: `${base}/settings`, label: "Settings", icon: "settings" },
  ];
  const isActive = (l: NavLink) => (l.exact ? pathname === l.href : pathname.startsWith(l.href));
  // Phone tab bar: the four things used daily; the rest live in "More".
  const tabKeys = isOwner ? ["Home", "Calendar", "Approvals", "Briefs"] : ["Home", "Briefs", "Calendar", "Runs"];
  const tabs = tabKeys.map((k) => all.find((l) => l.label === k)!);
  const moreLinks = all.filter((l) => !tabKeys.includes(l.label));
  const moreActive = moreLinks.some(isActive);

  const signOut = async () => { await api.logout(); window.location.assign("/login"); };

  return (
    <WorkspaceContext.Provider value={{ workspace: ws.data, role, isOwner, reload: ws.reload }}>
      <div className="shell">
        {/* Desktop sidebar */}
        <aside className="sidebar" aria-label="Workspace">
          <Link href="/" className="brand"><Logo size={30} />CreatorOps</Link>
          <Link href="/" className="sidebar-ws" title="Switch workspace">
            <Avatar name={ws.data.name} size={34} />
            <span className="grow" style={{ display: "grid", lineHeight: 1.25 }}>
              <strong style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{ws.data.name}</strong>
              <span className="muted small" style={{ textTransform: "capitalize" }}>{role}</span>
            </span>
            <Icon name="swap" size={16} className="chev" />
          </Link>
          <nav style={{ display: "grid", gap: 2 }} aria-label="Pages">
            {all.map((l) => (
              <Link key={l.href} href={l.href} className="side-link" aria-current={isActive(l) ? "page" : undefined}>
                <Icon name={l.icon} />
                {l.label}
                {!!l.count && <span className="count">{l.count}</span>}
              </Link>
            ))}
          </nav>
          <div className="sidebar-foot">
            <BellButton unread={notes.unread} open={bell} onClick={() => setBell((o) => !o)} />
            <button className="side-link" onClick={signOut} style={{ background: "none", border: 0, justifyContent: "flex-start", borderRadius: 12, padding: "10px 12px", minHeight: 0 }}>
              <Icon name="logout" />Sign out
            </button>
          </div>
        </aside>

        {/* Phone header */}
        <div>
          <header className="mobile-head">
            <Link href="/" aria-label="All workspaces" style={{ display: "flex" }}><Logo size={30} /></Link>
            <span className="ws-name grow">{ws.data.name}</span>
            <BellButton unread={notes.unread} open={bell} onClick={() => setBell((o) => !o)} label={false} />
          </header>
          <main className="content" key={pathname}>
            <div className="page">{children}</div>
          </main>
        </div>

        {/* Phone tab bar */}
        <nav className="tabbar" aria-label="Primary">
          {tabs.map((l) => (
            <Link key={l.href} href={l.href} className="tab" aria-current={isActive(l) ? "page" : undefined}>
              <Icon name={l.icon} size={22} />
              {l.label}
              {!!l.count && <span className="count badge-count">{l.count}</span>}
            </Link>
          ))}
          <button className="tab" onClick={() => setMore(true)} aria-haspopup="dialog" aria-expanded={more} aria-current={moreActive ? "page" : undefined} style={{ minHeight: 0, borderRadius: 14, border: 0 }}>
            <Icon name="more" size={22} />
            More
          </button>
        </nav>

        {more && (
          <>
            <div className="scrim" onClick={() => setMore(false)} />
            <div className="sheet" role="dialog" aria-label="More" aria-modal="true">
              <div className="sheet-grip" />
              <h2>{ws.data.name}</h2>
              {moreLinks.map((l) => (
                <Link key={l.href} href={l.href} className="sheet-link" aria-current={isActive(l) ? "page" : undefined}>
                  <span className="ico"><Icon name={l.icon} /></span>
                  {l.label}
                </Link>
              ))}
              <Link href="/" className="sheet-link"><span className="ico"><Icon name="swap" /></span>Switch workspace</Link>
              <button className="sheet-link" onClick={signOut}><span className="ico"><Icon name="logout" /></span>Sign out</button>
            </div>
          </>
        )}

        {bell && <NotificationPanel workspaceId={workspaceId} items={notes.items} reload={notes.reload} onClose={() => setBell(false)} />}
        <InstallPrompt />
      </div>
    </WorkspaceContext.Provider>
  );
}
