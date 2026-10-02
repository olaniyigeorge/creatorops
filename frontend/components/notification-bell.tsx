"use client";
import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";
import { api, type Notification } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { Icon } from "./icons";
import { fmtDate } from "./ui";

/** One poller per workspace (every 15s, so a newly escalated approval shows up without a refresh). */
export function useNotifications(workspaceId: string) {
  const state = useAsync(() => api.notifications(workspaceId), [workspaceId], {
    everyMs: 15000,
    shouldPoll: () => true,
  });
  const items: Notification[] = state.data ?? [];
  return { items, unread: items.filter((n) => !n.read_at).length, reload: state.reload };
}

/** The bell button. It only toggles; the panel is <NotificationPanel/>, mounted once by the layout. */
export function BellButton({ unread, open, onClick, label = true }: { unread: number; open: boolean; onClick: () => void; label?: boolean }) {
  return (
    <button
      type="button"
      className={label ? "side-link bell-side" : "icon-btn"}
      aria-label={`Notifications, ${unread} unread`}
      aria-expanded={open}
      onClick={onClick}
      style={label ? { background: "none", border: 0, width: "100%", justifyContent: "flex-start", borderRadius: 12, padding: "10px 12px", minHeight: 0 } : undefined}
    >
      <Icon name="bell" size={label ? 20 : 22} />
      {label && "Notifications"}
      {unread > 0 && <span className="count" style={label ? undefined : { position: "absolute", top: 4, right: 3 }}>{unread > 9 ? "9+" : unread}</span>}
    </button>
  );
}

export function NotificationPanel({ workspaceId, items, reload, onClose }: {
  workspaceId: string; items: Notification[]; reload: () => void; onClose: () => void;
}) {
  const router = useRouter();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    ref.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const unread = items.filter((n) => !n.read_at);

  return (
    <>
      <div className="scrim" onClick={onClose} style={{ background: "transparent", backdropFilter: "none" }} />
      <div className="popover" role="dialog" aria-label="Notifications" tabIndex={-1} ref={ref}>
        <div className="popover-head">
          <span>Notifications</span>
          <button className="icon-btn" aria-label="Close" onClick={onClose} style={{ width: 36, height: 36, minHeight: 36 }}><Icon name="close" size={18} /></button>
        </div>
        {items.length === 0 && <p className="muted" style={{ padding: "8px 16px 22px" }}>You&apos;re all caught up.</p>}
        {items.map((n) => (
          <button
            key={n.id}
            className={`notif ${n.read_at ? "" : "unread"}`}
            onClick={async () => {
              onClose();
              if (!n.read_at) await api.markRead(workspaceId, n.id).catch(() => undefined);
              reload();
              if (n.link) router.push(n.link);
            }}
          >
            {n.read_at ? <span className="read-dot" /> : <span className="unread-dot" />}
            <span style={{ display: "grid", gap: 2 }}>
              <span>{n.title}</span>
              <span className="muted small" style={{ fontWeight: 450 }}>{n.body ? `${n.body} · ` : ""}{fmtDate(n.created_at)}</span>
            </span>
          </button>
        ))}
        {unread.length > 0 && (
          <button
            className="ghost sm"
            style={{ margin: 8, width: "calc(100% - 16px)" }}
            onClick={async () => {
              await Promise.all(unread.map((n) => api.markRead(workspaceId, n.id).catch(() => undefined)));
              reload();
            }}
          >
            Mark all as read
          </button>
        )}
      </div>
    </>
  );
}
