"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { ErrorBox } from "@/components/ui";
import { Icon, Logo } from "@/components/icons";

const DEV_LOGIN = process.env.NEXT_PUBLIC_DEV_LOGIN === "true";

function safeNext(next: string | null): string {
  // Only same-site paths: never bounce to an attacker-supplied URL.
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

function GoogleG() {
  return (
    <svg width="20" height="20" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.9 6.1C12.4 13.6 17.7 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.5 5.8c4.4-4.1 7.1-10.1 7.1-17.5z" />
      <path fill="#FBBC05" d="M10.5 28.7a14.5 14.5 0 0 1 0-9.4l-7.9-6.1a24 24 0 0 0 0 21.6l7.9-6.1z" />
      <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.5-5.8c-2.1 1.4-4.8 2.3-8.4 2.3-6.3 0-11.6-4.1-13.5-9.8l-7.9 6.1C6.5 42.6 14.6 48 24 48z" />
    </svg>
  );
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
    <main className="auth">
      <div className="auth-card">
        <div className="auth-logo"><Logo size={72} /></div>
        <h1>CreatorOps</h1>
        <p className="tag">Your AI marketing manager for YouTube.</p>

        <div className="auth-panel">
          {/* Full-page navigation on purpose: the backend redirects through Google and back. */}
          <a
            className="btn google-btn"
            href="/api/auth/google/login"
            onClick={() => { try { sessionStorage.setItem("postLoginNext", next); } catch { /* ignore */ } }}
          >
            <GoogleG />
            Continue with Google
          </a>

          {DEV_LOGIN && (
            <form onSubmit={devLogin}>
              <div className="divider">dev login · local only</div>
              <label htmlFor="dev-email">Email</label>
              <input id="dev-email" type="email" inputMode="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
              <label htmlFor="dev-name">Name <span className="hint">(optional)</span></label>
              <input id="dev-name" type="text" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
              <ErrorBox message={error} />
              <button className="primary block" style={{ marginTop: 16 }} disabled={busy || !email}>{busy ? "Signing in…" : "Sign in"}</button>
            </form>
          )}
        </div>

        <div className="features">
          <div><Icon name="sparkle" size={18} />Researches your niche and plans the calendar</div>
          <div><Icon name="shield" size={18} />You choose how much it may do alone</div>
          <div><Icon name="film" size={18} />Briefs and chases your editors for you</div>
        </div>
      </div>
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
