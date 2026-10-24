import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Rocket, Loader2 } from "lucide-react";
import GlassPanel from "../components/GlassPanel";
import { submitMission, fetchPresets } from "../lib/api";

export default function NewSession() {
  const [mode, setMode] = useState("preset"); // preset | custom
  const [selectedPreset, setSelectedPreset] = useState(0);
  const [presets, setPresets] = useState(null);
  const [presetError, setPresetError] = useState(null);
  const [submitError, setSubmitError] = useState(null);
  const [name, setName] = useState("");
  const [launchDate, setLaunchDate] = useState("");
  const [context, setContext] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    fetchPresets()
      .then((p) => { if (!cancelled) setPresets(p); })
      .catch((e) => { if (!cancelled) setPresetError(e.message); });
    return () => { cancelled = true; };
  }, []);

  const preset = presets?.[selectedPreset];
  const canSubmit = mode === "preset" ? Boolean(preset) : name.trim().length >= 3 && launchDate;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setSubmitError(null);
    const payload = mode === "preset" ? preset : { name, launchDate, context };
    try {
      const { missionId } = await submitMission(payload);
      navigate(`/debate/${missionId}`);
    } catch (err) {
      setSubmitError(err.message);
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-4 pt-14 pb-24">
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
        <span className="inline-flex items-center gap-2 text-xs font-medium text-judge-600 bg-judge-500/10 rounded-full px-3 py-1 ring-1 ring-judge-500/20 mb-5">
          <Rocket size={12} /> New mission review
        </span>
        <h1 className="font-display text-4xl text-ink-900 mb-3">
          Put a launch date on trial.
        </h1>
        <p className="text-ink-500 mb-10 max-w-xl">
          Four domain agents will argue over the plan — solar weather, fuel
          logistics, crew readiness, and mission value — until the Judge is
          satisfied the conclusion holds.
        </p>
      </motion.div>

      <GlassPanel className="p-6 sm:p-8">
        <div className="flex gap-2 mb-6">
          {[
            { id: "preset", label: "Choose a mission" },
            { id: "custom", label: "Custom mission" },
          ].map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setMode(t.id)}
              className={`focus-ring flex-1 rounded-xl px-4 py-2.5 text-sm font-medium border transition-all ${
                mode === t.id
                  ? "border-judge-500 bg-judge-500/10 text-judge-600"
                  : "border-ink-900/10 bg-white/50 text-ink-700 hover:bg-white/80"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {mode === "preset" ? (
            <div className="space-y-3">
              {presetError && <p className="text-sm text-crew-500">Could not load missions: {presetError}. You can still enter a custom mission.</p>}
              {!presets && !presetError && [0, 1, 2].map((i) => <div key={i} className="h-24 rounded-xl bg-ink-900/5 animate-pulse" />)}
              {presets?.map((m, i) => (
                <button
                  type="button"
                  key={m.name}
                  onClick={() => setSelectedPreset(i)}
                  className={`focus-ring w-full text-left rounded-xl px-4 py-3.5 border transition-all ${
                    selectedPreset === i
                      ? "border-judge-500 bg-judge-500/10"
                      : "border-ink-900/10 bg-white/50 hover:bg-white/80"
                  }`}
                >
                  <p className="font-medium text-ink-900">{m.name}</p>
                  <p className="text-xs text-ink-500 mt-1 font-mono">
                    Target launch: {new Date(m.launchDate + "T00:00:00").toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" })}
                  </p>
                  <p className="text-sm text-ink-700 mt-1.5">{m.context}</p>
                </button>
              ))}
            </div>
          ) : (
            <>
              <div>
                <label className="block text-sm font-medium text-ink-900 mb-2">Mission name</label>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Meridian Mars Transfer Window"
                  required
                  className="focus-ring w-full rounded-xl bg-white/70 border border-ink-900/10 px-4 py-3 text-ink-900 placeholder:text-ink-500/60"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink-900 mb-2">Target launch date</label>
                <input
                  type="date"
                  value={launchDate}
                  onChange={(e) => setLaunchDate(e.target.value)}
                  required
                  className="focus-ring w-full rounded-xl bg-white/70 border border-ink-900/10 px-4 py-3 text-ink-900"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink-900 mb-2">
                  Mission context <span className="text-ink-500 font-normal">(optional)</span>
                </label>
                <textarea
                  value={context}
                  onChange={(e) => setContext(e.target.value)}
                  placeholder="Crew size, cargo, trajectory notes..."
                  rows={3}
                  className="focus-ring w-full rounded-xl bg-white/70 border border-ink-900/10 px-4 py-3 text-ink-900 placeholder:text-ink-500/60 resize-none"
                />
              </div>
            </>
          )}

          <div className="rounded-xl bg-ink-900/5 px-4 py-3 text-xs text-ink-500">
            Four agents (Astro-Weather, Logistics, Crew Readiness, Mission Value) debate over
            several rounds, then the Judge rules. Astro-Weather is grounded on NOAA's solar-cycle
            forecast where it covers your launch month; other figures the agents raise are labelled
            as assumptions.
          </div>
          {submitError && <p role="alert" className="text-sm text-crew-500">{submitError}</p>}

          <button
            type="submit"
            disabled={submitting || !canSubmit}
            className="focus-ring w-full inline-flex items-center justify-center gap-2 bg-judge-500 hover:bg-judge-600 disabled:opacity-60 disabled:cursor-not-allowed transition-colors text-white font-medium px-6 py-3.5 rounded-xl shadow-glass-lg"
          >
            <AnimatePresence mode="wait" initial={false}>
              {submitting ? (
                <motion.span key="loading" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="inline-flex items-center gap-2">
                  <Loader2 size={16} className="animate-spin" />
                  Dispatching to agents...
                </motion.span>
              ) : (
                <motion.span key="idle" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                  Open the debate
                </motion.span>
              )}
            </AnimatePresence>
          </button>
        </form>
      </GlassPanel>
    </div>
  );
}
