"use client";
import { useEffect, useState } from "react";
import { Icon } from "./icons";

interface InstallEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

const DISMISSED_KEY = "pwa-install-dismissed";

/** Registers the service worker (production only: it would fight HMR in dev). */
export function PwaRegister() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production" || !("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js", { scope: "/", updateViaCache: "none" }).catch(() => undefined);
  }, []);
  return null;
}

/** A small "Install app" banner, shown only when the browser says the app is installable. */
export function InstallPrompt() {
  const [event, setEvent] = useState<InstallEvent>();

  useEffect(() => {
    try { if (localStorage.getItem(DISMISSED_KEY)) return; } catch { /* storage unavailable */ }
    const onPrompt = (e: Event) => { e.preventDefault(); setEvent(e as InstallEvent); };
    const onInstalled = () => setEvent(undefined);
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  if (!event) return null;
  const dismiss = () => {
    try { localStorage.setItem(DISMISSED_KEY, "1"); } catch { /* ignore */ }
    setEvent(undefined);
  };
  return (
    <div className="install" role="region" aria-label="Install app">
      <div className="install-text">
        <strong>Install CreatorOps</strong>
        <span>Add it to your home screen for a full-screen app.</span>
      </div>
      <button className="btn primary sm" onClick={async () => { await event.prompt(); setEvent(undefined); }}>Install</button>
      <button className="icon-btn" aria-label="Dismiss" onClick={dismiss}><Icon name="close" /></button>
    </div>
  );
}
