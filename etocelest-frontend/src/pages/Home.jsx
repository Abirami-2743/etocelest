import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, Sun, Fuel, Users, Sparkles } from "lucide-react";
import GlassPanel from "../components/GlassPanel";
import { listMissions } from "../lib/api";

const AGENT_CARDS = [
  {
    id: "astro",
    icon: Sun,
    name: "Astro-Weather",
    desc: "Tracks solar activity and radiation exposure risk across the launch window.",
    accent: "text-astro-500",
    ring: "ring-astro-500/20",
    bg: "bg-astro-500/10",
  },
  {
    id: "logistics",
    icon: Fuel,
    name: "Logistics",
    desc: "Weighs fuel cost, procurement contracts, and the price of holding a delay.",
    accent: "text-logistics-500",
    ring: "ring-logistics-500/20",
    bg: "bg-logistics-500/10",
  },
  {
    id: "crew",
    icon: Users,
    name: "Crew Readiness",
    desc: "Protects crew size, training curves, and life-support margins.",
    accent: "text-crew-500",
    ring: "ring-crew-500/20",
    bg: "bg-crew-500/10",
  },
  {
    id: "missionvalue",
    icon: Sparkles,
    name: "Mission Value",
    desc: "Argues for scientific return, trajectory, and public engagement value.",
    accent: "text-missionvalue-500",
    ring: "ring-missionvalue-500/20",
    bg: "bg-missionvalue-500/10",
  },
];

export default function Home() {
  const navigate = useNavigate();
  const [latest, setLatest] = useState(null);

  useEffect(() => {
    let cancelled = false;
    listMissions()
      .then((all) => { if (!cancelled) setLatest(all.find((m) => m.status === "complete") || null); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="max-w-6xl mx-auto px-4">
      <section className="pt-16 pb-20 grid lg:grid-cols-[1.15fr_0.85fr] gap-12 items-center">
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: [0.2, 0.6, 0.3, 1] }}>
          <span className="inline-flex items-center gap-2 text-xs font-medium text-judge-600 bg-judge-500/10 rounded-full px-3 py-1 ring-1 ring-judge-500/20">
            Multi-agent adversarial reasoning
          </span>
          <h1 className="font-display text-5xl sm:text-6xl leading-[1.05] mt-5 text-ink-900">
            No launch date survives without a cross-examination.
          </h1>
          <p className="mt-6 text-lg text-ink-700 max-w-xl leading-relaxed">
            ÉTOCELEST puts a mission plan on trial before it's committed. Four
            domain agents argue solar risk, fuel cost, crew readiness, and
            mission value against each other — a Judge reads every round,
            sends the debate back where objections are unanswered, and always
            issues a ruling.
          </p>
          <div className="mt-9 flex flex-wrap items-center gap-4">
            <button
              onClick={() => navigate("/new")}
              className="focus-ring group inline-flex items-center gap-2 bg-judge-500 hover:bg-judge-600 transition-colors text-white font-medium px-6 py-3.5 rounded-xl shadow-glass-lg"
            >
              Start a mission review
              <ArrowRight size={16} className="transition-transform group-hover:translate-x-0.5" />
            </button>
            <button
              onClick={() => navigate("/how-it-works")}
              className="focus-ring text-ink-700 font-medium px-6 py-3.5 rounded-xl hover:bg-ink-900/5 transition-colors"
            >
              See how it reasons
            </button>
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.7, delay: 0.15, ease: [0.2, 0.6, 0.3, 1] }} className="relative">
          <GlassPanel className="p-6 relative overflow-hidden">
            <img
              src="https://images.unsplash.com/photo-1516849841032-87cbac4d88f7?q=80&w=900&auto=format&fit=crop"
              alt="Rocket on a launch pad at dawn"
              className="w-full h-56 object-cover rounded-xl"
            />
            <div className="mt-5 space-y-3">
              {latest ? (
                <>
                  <div className="flex items-center justify-between text-xs font-mono text-ink-500">
                    <span className="truncate">mission_{latest.id.slice(0, 6)} — {latest.name}</span>
                    <span className="text-astro-500 shrink-0">● ruled</span>
                  </div>
                  <p className="text-sm text-ink-700 leading-relaxed">
                    <span className="font-medium text-ink-900">Ruling:</span> {latest.verdict} — confidence {latest.confidence}%
                  </p>
                  <div className="h-1.5 rounded-full bg-ink-900/5 overflow-hidden">
                    <div className="h-full bg-gradient-to-r from-judge-500 to-astro-400 rounded-full" style={{ width: `${latest.confidence}%` }} />
                  </div>
                </>
              ) : (
                <p className="text-sm text-ink-700 leading-relaxed">
                  Your most recent ruling will appear here once you have completed a mission review.
                </p>
              )}
            </div>
          </GlassPanel>
        </motion.div>
      </section>

      <section className="pb-20">
        <h2 className="font-display text-3xl text-ink-900 mb-2">Four domains, one ruling</h2>
        <p className="text-ink-500 max-w-2xl mb-10">
          Every mission runs through the same structure of formal debate — no
          single model decides the launch date alone.
        </p>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {AGENT_CARDS.map((a, i) => (
            <motion.div key={a.id} initial={{ opacity: 0, y: 14 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-60px" }} transition={{ duration: 0.5, delay: i * 0.06 }}>
              <GlassPanel className="p-5 h-full hover:shadow-glass-lg transition-shadow">
                <div className={`inline-flex items-center justify-center w-10 h-10 rounded-xl ${a.bg} ring-1 ${a.ring} mb-4`}>
                  <a.icon size={18} className={a.accent} strokeWidth={2.2} />
                </div>
                <h3 className="font-display text-xl text-ink-900 mb-1.5">{a.name}</h3>
                <p className="text-sm text-ink-500 leading-relaxed">{a.desc}</p>
              </GlassPanel>
            </motion.div>
          ))}
        </div>
      </section>

      <section className="pb-24 grid lg:grid-cols-2 gap-8 items-center">
        <motion.img
          initial={{ opacity: 0, x: -16 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          src="https://images.unsplash.com/photo-1541185933-ef5d8ed016c2?q=80&w=1000&auto=format&fit=crop"
          alt="Mission control room monitoring a launch"
          className="rounded-2xl shadow-glass-lg object-cover h-72 w-full"
        />
        <div>
          <h2 className="font-display text-3xl text-ink-900 mb-4">Built for launches that can't afford to guess</h2>
          <p className="text-ink-700 leading-relaxed mb-4">
            A single-pass go/no-go call hides its assumptions. ÉTOCELEST
            forces every domain to defend its position out loud — and the
            Judge sends the debate back for another round until the
            conclusion actually holds up.
          </p>
          <ul className="space-y-3 text-sm text-ink-700">
            {[
              "Every claim is attributed to the domain agent that made it",
              "The Judge re-opens debate until objections are resolved",
              "Confidence and any recommended date shift are reported explicitly",
            ].map((t) => (
              <li key={t} className="flex items-start gap-2.5">
                <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-judge-500 shrink-0" />
                {t}
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}
