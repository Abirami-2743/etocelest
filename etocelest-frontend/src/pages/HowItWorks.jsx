import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import GlassPanel from "../components/GlassPanel";

const STEPS = [
  {
    title: "Submit the mission",
    desc: "Pick a mission or enter your own: name, target launch date, and any context — crew size, cargo, trajectory notes.",
    img: "https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=800&auto=format&fit=crop",
  },
  {
    title: "Round 1 — opening positions",
    desc: "Astro-Weather, Logistics, Crew Readiness, and Mission Value each state their domain's read, a proposed delay, and the range they could accept. Astro-Weather works from NOAA's solar-cycle forecast where it covers your date.",
    img: "https://images.unsplash.com/photo-1614728263952-84ea256f9679?q=80&w=800&auto=format&fit=crop",
  },
  {
    title: "The Judge checks for gaps",
    desc: "After every round, the Judge checks whether the four domains actually reconcile. If not, it names exactly what's unresolved and sends the debate back.",
    img: "https://images.unsplash.com/photo-1567095761054-7a02e69e5c43?q=80&w=800&auto=format&fit=crop",
  },
  {
    title: "Rounds repeat until resolved",
    desc: "Agents answer each other and the Judge's named questions in the next round, and may move their positions. This continues until the Judge is satisfied or the round cap is reached.",
    img: "https://images.unsplash.com/photo-1517976487492-5750f3195933?q=80&w=800&auto=format&fit=crop",
  },
  {
    title: "Final ruling",
    desc: "The Judge always rules: proceed as planned, or shift the launch by a bounded window. If the cap is reached without consensus the ruling is marked as forced and its confidence is lowered.",
    img: "https://images.unsplash.com/photo-1517976384346-3136801d605d?q=80&w=800&auto=format&fit=crop",
  },
];

export default function HowItWorks() {
  const navigate = useNavigate();
  return (
    <div className="max-w-4xl mx-auto px-4 pt-14 pb-24">
      <h1 className="font-display text-4xl text-ink-900 mb-3">How the debate works</h1>
      <p className="text-ink-500 max-w-xl mb-14">
        Round after round, one transcript. Nothing about the launch date is
        decided until every objection has had a chance to land.
      </p>

      <div className="space-y-6">
        {STEPS.map((step, i) => (
          <motion.div key={step.title} initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-80px" }} transition={{ duration: 0.5, delay: i * 0.05 }}>
            <GlassPanel className="p-6 sm:p-7 grid sm:grid-cols-[auto_1fr_auto] gap-5 items-center">
              <span className="font-display text-3xl text-judge-500/30 sm:w-10">{String(i + 1).padStart(2, "0")}</span>
              <div>
                <h3 className="font-display text-xl text-ink-900 mb-1.5">{step.title}</h3>
                <p className="text-sm text-ink-700 leading-relaxed max-w-lg">{step.desc}</p>
              </div>
              <img src={step.img} alt="" className="hidden sm:block w-28 h-20 object-cover rounded-xl" />
            </GlassPanel>
          </motion.div>
        ))}
      </div>

      <div className="mt-12 text-center">
        <button
          onClick={() => navigate("/new")}
          className="focus-ring bg-judge-500 hover:bg-judge-600 transition-colors text-white font-medium px-7 py-3.5 rounded-xl shadow-glass-lg"
        >
          Try it on a mission
        </button>
      </div>
    </div>
  );
}
