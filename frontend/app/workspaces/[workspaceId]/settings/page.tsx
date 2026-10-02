"use client";
import { useState } from "react";
import { api, errorMessage, type Autonomy, type WorkspaceUpdate } from "@/lib/api";
import { ErrorBox, Notice, PageHeader } from "@/components/ui";
import { Icon } from "@/components/icons";
import { useWorkspace } from "@/components/workspace-context";

const LEVELS: { value: Autonomy; title: string; text: string }[] = [
  { value: "low", title: "Low", text: "You approve almost everything. Best while you build trust: every judgment call is shown to you first." },
  { value: "medium", title: "Medium", text: "Routine work (titles, descriptions, status emails) runs by itself. Strategy, calendar, publishing and AI video wait for your approval." },
  { value: "high", title: "High", text: "The agent runs approved workflows on its own using its best judgment. Guardrails still apply, and the first few publishes always need you." },
];

export default function SettingsPage() {
  const { workspace: w, isOwner, reload } = useWorkspace();
  const [name, setName] = useState(w.name);
  const [autonomy, setAutonomy] = useState<Autonomy>(w.autonomy);
  const [threshold, setThreshold] = useState(w.guardrail_threshold);
  const [floor, setFloor] = useState(w.publish_human_floor);
  const [video, setVideo] = useState(w.video_gen_enabled);
  const [budget, setBudget] = useState(w.video_budget_usd);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string>();
  const touch = () => setSaved(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(undefined);
    const patch: WorkspaceUpdate = {
      name: name.trim(), autonomy, guardrail_threshold: threshold,
      publish_human_floor: floor, video_gen_enabled: video, video_budget_usd: budget,
    };
    try {
      await api.updateWorkspace(w.id, patch);
      setSaved(true);
      reload();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  const ro = !isOwner;
  return (
    <>
      <PageHeader title="Settings" subtitle="How much the agent may do on its own, and its limits." />
      {ro && <Notice icon="shield">Only the workspace owner can change settings.</Notice>}
      <form onSubmit={submit}>
        <div className="card pad-lg">
          <label htmlFor="name" style={{ marginTop: 0 }}>Workspace name</label>
          <input id="name" type="text" required disabled={ro} value={name} onChange={(e) => { setName(e.target.value); touch(); }} />
        </div>

        <fieldset disabled={ro}>
          <legend>AI autonomy</legend>
          {LEVELS.map((l) => (
            <label key={l.value} className="choice">
              <input type="radio" name="autonomy" checked={autonomy === l.value} onChange={() => { setAutonomy(l.value); touch(); }} />
              <span><strong>{l.title}</strong><span className="muted">{l.text}</span></span>
            </label>
          ))}
        </fieldset>

        <div className="card pad-lg" style={{ marginTop: 18 }}>
          <h3>Guardrails</h3>
          <label htmlFor="threshold">Guardrail threshold <span className="hint">(0 to 1)</span></label>
          <input id="threshold" type="number" inputMode="decimal" min={0} max={1} step={0.05} disabled={ro} value={threshold} onChange={(e) => { setThreshold(Number(e.target.value)); touch(); }} />
          <p className="field-help">Generated content scoring below this is regenerated, then escalated.</p>
          <label htmlFor="floor">Publishes that always need approval</label>
          <input id="floor" type="number" inputMode="numeric" min={0} step={1} disabled={ro} value={floor} onChange={(e) => { setFloor(Number(e.target.value)); touch(); }} />
          <p className="field-help">Applies even at High autonomy.</p>
        </div>

        <fieldset disabled={ro}>
          <legend>AI video generation</legend>
          <label className="switch-row">
            <span>Allow the agent to propose AI-generated video. Below High autonomy you trigger each generation.</span>
            <input type="checkbox" checked={video} onChange={(e) => { setVideo(e.target.checked); touch(); }} />
            <span className="switch" aria-hidden="true" />
          </label>
          <label htmlFor="budget">Budget (USD)</label>
          <input id="budget" type="number" inputMode="decimal" min={0} step={1} value={budget} onChange={(e) => { setBudget(Number(e.target.value)); touch(); }} />
          <p className="field-help">Spent so far: <strong>${w.video_spent_usd.toFixed(2)}</strong> (read-only).</p>
        </fieldset>

        <ErrorBox message={error} />
        {saved && <Notice tone="ok" icon="check">Saved.</Notice>}
        {!ro && (
          <div className="sticky-actions">
            <button className="primary block" disabled={saving}>{saving ? "Saving…" : <><Icon name="check" size={18} />Save settings</>}</button>
          </div>
        )}
      </form>
    </>
  );
}
