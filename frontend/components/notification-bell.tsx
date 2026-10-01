"use client";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { fmtDate } from "./ui";

export function NotificationBell({ workspaceId }: { workspaceId: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  // Poll every 15s so a newly escalated approval shows up without a refresh.
  const { data, reload } = useAsync(() => api.notifications(workspaceId), [workspaceId], {
    everyMs: 15000,
    shouldPoll: () => true,
  });
  const unread = (data ?? []).filter((n) => !n.read_at);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  return (
    <div className="bell" ref={ref}>
      <button
        type="button"
        aria-label={`Notifications, ${unread.length} unread`}
        aria-expanded={open}
        onClick={() => { setOpen((o) => !o); reload(); }}
      >
        🔔
        {unread.length > 0 && <span className="bell-count">{unread.length}</span>}
      </button>
      {open && (
        <div className="dropdown" role="menu">
          {(data ?? []).length === 0 && <p className="muted" style={{ padding: ".6rem .8rem" }}>No notifications.</p>}
          {(data ?? []).map((n) => (
            <button
              key={n.id}
              className={`item ${n.read_at ? "" : "unread"}`}
              onClick={async () => {
                setOpen(false);
                if (!n.read_at) await api.markRead(workspaceId, n.id).catch(() => undefined);
                reload();
                if (n.link) router.push(n.link);
              }}
            >
              <div>{n.title}</div>
              <div className="muted small">{n.body ? `${n.body} · ` : ""}{fmtDate(n.created_at)}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
