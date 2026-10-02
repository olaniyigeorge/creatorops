"use client";
import { useEffect, useState } from "react";
import { api, errorMessage, type ChannelProfile, type Goal } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import { ErrorBox, Loading, Notice, PageHeader } from "@/components/ui";
import { Icon } from "@/components/icons";
import { useWorkspace } from "@/components/workspace-context";

const lines = (s: string) => s.split("\n").map((l) => l.trim()).filter(Boolean);

export default function OnboardingPage() {
  const { workspace, isOwner } = useWorkspace();
  const id = workspace.id;
  const existing = useAsync(() => api.onboarding(id), [id]);
  const [f, setF] = useState({
    channel_name: workspace.name, goal: "growth" as Goal, audience: "", tone: "", brand_voice: "",
    niche_hint: "", banned: "", rules: "", competitors: "", videos_per_week: 2, region_code: "US",
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string>();

  useEffect(() => {
    const p = existing.data;
    if (!p) return;
    setF({
      channel_name: p.channel_name, goal: p.goal, audience: p.audience, tone: p.tone,
      brand_voice: p.brand_voice, niche_hint: p.niche_hint ?? "", banned: p.banned_topics.join("\n"),
      rules: p.extra_rules.join("\n"), competitors: p.competitors.join("\n"),
      videos_per_week: p.videos_per_week, region_code: p.region_code,
    });
  }, [existing.data]);

  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => { setF((s) => ({ ...s, [k]: v })); setSaved(false); };

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(undefined);
    const body: ChannelProfile = {
      channel_name: f.channel_name.trim(), goal: f.goal, audience: f.audience.trim(), tone: f.tone.trim(),
      brand_voice: f.brand_voice.trim(), niche_hint: f.niche_hint.trim() || null,
      banned_topics: lines(f.banned), extra_rules: lines(f.rules), competitors: lines(f.competitors),
      videos_per_week: Number(f.videos_per_week), region_code: f.region_code.trim().toUpperCase(),
    };
    try {
      await api.saveOnboarding(id, body);
      setSaved(true);
      existing.reload();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  if (existing.loading) return <Loading />;
  const ro = !isOwner;
  return (
    <>
      <PageHeader title="Onboarding" subtitle="These answers shape every strategy and creative the agent produces, and become the guardrail rubric it is checked against." />
      {ro && <Notice icon="shield">Only the workspace owner can edit these answers.</Notice>}
      <form onSubmit={submit}>
        <div className="card pad-lg">
          <h3>Your channel</h3>
          <label htmlFor="channel_name">Channel name</label>
          <input id="channel_name" type="text" required maxLength={200} disabled={ro} value={f.channel_name} onChange={(e) => set("channel_name", e.target.value)} />

          <label htmlFor="goal">Main goal</label>
          <select id="goal" disabled={ro} value={f.goal} onChange={(e) => set("goal", e.target.value as Goal)}>
            <option value="growth">Growth: reach more viewers</option>
            <option value="monetization">Monetization: become revenue-ready</option>
            <option value="engagement">Engagement: deepen community</option>
          </select>

          <label htmlFor="niche_hint">Niche idea <span className="hint">(optional)</span></label>
          <input id="niche_hint" type="text" maxLength={200} disabled={ro} value={f.niche_hint} onChange={(e) => set("niche_hint", e.target.value)} />

          <div className="grid" style={{ marginTop: 4 }}>
            <div>
              <label htmlFor="vpw">Videos per week</label>
              <input id="vpw" type="number" inputMode="numeric" min={1} max={14} required disabled={ro} value={f.videos_per_week} onChange={(e) => set("videos_per_week", Number(e.target.value))} />
            </div>
            <div>
              <label htmlFor="region">Region code <span className="hint">(2 letters)</span></label>
              <input id="region" type="text" autoCapitalize="characters" required pattern="[A-Za-z]{2}" maxLength={2} disabled={ro} value={f.region_code} onChange={(e) => set("region_code", e.target.value)} />
            </div>
          </div>
        </div>

        <div className="card pad-lg" style={{ marginTop: 14 }}>
          <h3>Audience &amp; voice</h3>
          <label htmlFor="audience">Target audience</label>
          <textarea id="audience" required maxLength={500} disabled={ro} value={f.audience} onChange={(e) => set("audience", e.target.value)} />

          <label htmlFor="tone">Tone</label>
          <input id="tone" type="text" required maxLength={300} disabled={ro} placeholder="e.g. friendly, practical, a bit nerdy" value={f.tone} onChange={(e) => set("tone", e.target.value)} />

          <label htmlFor="brand_voice">Brand voice <span className="hint">(optional)</span></label>
          <textarea id="brand_voice" maxLength={1000} disabled={ro} value={f.brand_voice} onChange={(e) => set("brand_voice", e.target.value)} />
        </div>

        <div className="card pad-lg" style={{ marginTop: 14 }}>
          <h3>Rules &amp; competitors</h3>
          <label htmlFor="banned">Topics to avoid <span className="hint">(one per line)</span></label>
          <textarea id="banned" disabled={ro} value={f.banned} onChange={(e) => set("banned", e.target.value)} />

          <label htmlFor="rules">Extra brand rules <span className="hint">(one per line)</span></label>
          <textarea id="rules" disabled={ro} value={f.rules} onChange={(e) => set("rules", e.target.value)} />

          <label htmlFor="competitors">Competitor channels <span className="hint">(up to 10, one per line: @handle, URL or channel id)</span></label>
          <textarea id="competitors" autoCapitalize="none" disabled={ro} value={f.competitors} onChange={(e) => set("competitors", e.target.value)} />
        </div>

        <ErrorBox message={error} />
        {saved && <Notice tone="ok" icon="check">Saved.</Notice>}
        {!ro && (
          <div className="sticky-actions">
            <button className="primary block" disabled={saving}>{saving ? "Saving…" : <><Icon name="check" size={18} />Save answers</>}</button>
          </div>
        )}
      </form>
    </>
  );
}
