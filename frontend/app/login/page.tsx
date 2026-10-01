"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { ErrorBox } from "@/components/ui";

const DEV_LOGIN = process.env.NEXT_PUBLIC_DEV_LOGIN === "true";

function safeNext(next: string | null): string {
  // Only same-site paths: never bounce to an attacker-supplied URL.
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

function LoginForm() {
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  async function devLogin(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await api.devLogin(email.trim(), name.trim() || undefined);
      router.replace(next);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <main className="narrow">
      <h1>CreatorOps</h1>
      <p className="muted">AI marketing operations for your YouTube channel.</p>
      {/* Full-page navigation on purpose: the backend redirects through Google and back. */}
      <a
        className="btn primary"
        href="/api/auth/google/login"
        onClick={() => { try { sessionStorage.setItem("postLoginNext", next); } catch { /* ignore */ } }}
      >
        Continue with Google
      </a>

      {DEV_LOGIN && (
        <form className="card" onSubmit={devLogin}>
          <h2 style={{ marginTop: 0 }}>Dev login</h2>
          <p className="muted small">Local testing only: signs in as any email, no Google needed.</p>
          <label htmlFor="dev-email">Email</label>
          <input id="dev-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <label htmlFor="dev-name">Name <span className="hint">(optional)</span></label>
          <input id="dev-name" type="text" value={name} onChange={(e) => setName(e.target.value)} />
          <ErrorBox message={error} />
          <p><button className="primary" disabled={busy || !email}>Sign in</button></p>
        </form>
      )}
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
