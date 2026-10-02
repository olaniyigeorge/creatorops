"use client";
import Link from "next/link";
import { useState } from "react";
import { Icon, type IconName } from "./icons";

export function ErrorBox({ message }: { message?: string }) {
  return message ? (
    <div className="alert" role="alert">
      <Icon name="alert" size={18} />
      <span>{message}</span>
    </div>
  ) : null;
}

export function Notice({ tone, icon, children }: { tone?: "ok" | "warn"; icon?: IconName; children: React.ReactNode }) {
  return (
    <div className={`notice ${tone ?? ""}`} role={tone === "ok" ? "status" : undefined}>
      {icon && <Icon name={icon} size={18} />}
      <div>{children}</div>
    </div>
  );
}

/** Skeleton placeholder while loading. `rows` stacked cards by default. */
export function Loading({ what = "Loading", rows = 3 }: { what?: string; rows?: number }) {
  return (
    <div className="stack" aria-busy="true" aria-live="polite">
      <span className="sr-only">{what}…</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton card-skel" style={{ animationDelay: `${i * 90}ms` }} />
      ))}
    </div>
  );
}

export function Spinner() {
  return <span className="spinner" role="status" aria-label="Working" />;
}

export function EmptyState({ icon = "inbox", title, children, action }: {
  icon?: IconName; title: string; children?: React.ReactNode; action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon"><Icon name={icon} size={26} /></div>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions, back }: {
  title: React.ReactNode; subtitle?: React.ReactNode; actions?: React.ReactNode; back?: { href: string; label: string };
}) {
  return (
    <header className="page-head">
      {back && <BackLink href={back.href}>{back.label}</BackLink>}
      <div className="page-head-row">
        <div className="page-head-text">
          <h1>{title}</h1>
          {subtitle && <p className="muted">{subtitle}</p>}
        </div>
        {actions && <div className="page-head-actions">{actions}</div>}
      </div>
    </header>
  );
}

export function BackLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link href={href} className="back">
      <Icon name="back" size={16} />
      {children}
    </Link>
  );
}

const TONE: Record<string, string> = {
  succeeded: "ok", executed: "ok", approved: "ok", submitted: "ok", done: "ok", briefed: "ok", complete: "ok",
  failed: "bad", rejected: "bad", blocked: "bad", overdue: "bad",
  waiting_approval: "warn", awaiting_approval: "warn", pending: "warn", draft: "warn",
  running: "info", assigned: "info", in_progress: "info",
};

export function StatusBadge({ status }: { status: string }) {
  const tone = TONE[status] ?? "";
  return (
    <span className={`badge ${tone}`}>
      <span className={`dot ${tone === "info" ? "pulse" : ""}`} />
      {status.replace(/_/g, " ")}
    </span>
  );
}

const AVATAR_COLORS = ["#e11d12", "#262626", "#9b1c13", "#4a4a4a", "#c2410c"];

export function Avatar({ name, size = 36 }: { name: string; size?: number }) {
  const initials = name.split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((p) => p[0]!.toUpperCase()).join("") || "?";
  let h = 0;
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) % 997;
  return (
    <span className="avatar" style={{ width: size, height: size, fontSize: size * 0.38, background: AVATAR_COLORS[h % AVATAR_COLORS.length] }} aria-hidden="true">
      {initials}
    </span>
  );
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function fmtDay(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      className="btn sm"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          setTimeout(() => setDone(false), 1500);
        } catch {
          window.prompt("Copy this:", text);
        }
      }}
    >
      <Icon name={done ? "check" : "copy"} size={16} />
      {done ? "Copied" : label}
    </button>
  );
}
