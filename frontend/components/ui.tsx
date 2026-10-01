"use client";
import { useState } from "react";

export function ErrorBox({ message }: { message?: string }) {
  return message ? <div className="alert" role="alert">{message}</div> : null;
}

export function Loading({ what = "Loading" }: { what?: string }) {
  return <p className="muted" aria-live="polite">{what}…</p>;
}

const TONE: Record<string, string> = {
  succeeded: "ok", executed: "ok", approved: "ok",
  failed: "bad", rejected: "bad", blocked: "bad",
  waiting_approval: "warn", awaiting_approval: "warn", pending: "warn",
  running: "info",
};

export function StatusBadge({ status }: { status: string }) {
  return <span className={`badge ${TONE[status] ?? ""}`}>{status.replace(/_/g, " ")}</span>;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
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
      {done ? "Copied" : label}
    </button>
  );
}
