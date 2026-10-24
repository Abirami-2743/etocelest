import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Plus, Trash2, ArrowUpRight } from "lucide-react";
import GlassPanel from "../components/GlassPanel";
import { listMissions, deleteMission } from "../lib/api";

function fmtDate(iso) {
  return new Date(iso + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function VerdictPill({ verdict }) {
  const tone = verdict?.startsWith("Shift")
    ? "bg-logistics-500/10 text-logistics-500"
    : verdict?.startsWith("Proceed")
    ? "bg-astro-500/10 text-astro-500"
    : "bg-ink-900/5 text-ink-500";
  return <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${tone}`}>{verdict}</span>;
}

export default function History() {
  const [missions, setMissions] = useState(null);
  const navigate = useNavigate();

  const [error, setError] = useState(null);

  async function load() {
    try {
      setError(null);
      setMissions(await listMissions());
    } catch (err) {
      setError(err.message);
      setMissions([]);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleDelete(id, e) {
    e.preventDefault();
    e.stopPropagation();
    try {
      await deleteMission(id);
    } catch (err) {
      setError(err.message);
      return;
    }
    load();
  }

  return (
    <div className="max-w-4xl mx-auto px-4 pt-12 pb-24">
      <div className="flex items-center justify-between mb-8 gap-4 flex-wrap">
        <div>
          <h1 className="font-display text-4xl text-ink-900 mb-2">Mission history</h1>
          <p className="text-ink-500">Every ruling, kept for the record.</p>
        </div>
        <button
          onClick={() => navigate("/new")}
          className="focus-ring inline-flex items-center gap-2 bg-judge-500 hover:bg-judge-600 transition-colors text-white font-medium px-5 py-2.5 rounded-xl shadow-glass"
        >
          <Plus size={16} /> New mission
        </button>
      </div>

      {missions === null && (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-24 rounded-2xl bg-ink-900/5 animate-pulse" />
          ))}
        </div>
      )}

      {error && <p role="alert" className="text-sm text-crew-500 mb-4">{error}</p>}

      {missions?.length === 0 && !error && (
        <GlassPanel className="p-12 text-center">
          <p className="text-ink-700 font-medium mb-1">No missions yet</p>
          <p className="text-ink-500 text-sm mb-6">Start one to see it appear here.</p>
          <button onClick={() => navigate("/new")} className="text-judge-600 font-medium focus-ring">
            Open a new mission review →
          </button>
        </GlassPanel>
      )}

      <div className="space-y-3">
        {missions?.map((m, i) => (
          <motion.div key={m.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: i * 0.04 }}>
            <Link to={m.status === "complete" ? `/verdict/${m.id}` : `/debate/${m.id}`}>
              <GlassPanel className="p-5 flex items-center justify-between gap-4 hover:shadow-glass-lg transition-shadow group">
                <div className="min-w-0">
                  <p className="font-medium text-ink-900 truncate mb-1.5">{m.name}</p>
                  <div className="flex items-center gap-2.5 flex-wrap">
                    {m.status === "complete" ? (
                      <VerdictPill verdict={m.verdict} />
                    ) : m.status === "failed" ? (
                      <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-crew-500/10 text-crew-500">Failed</span>
                    ) : (
                      <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-judge-500/10 text-judge-600">In progress</span>
                    )}
                    <span className="text-xs text-ink-500 font-mono">Launch target: {fmtDate(m.launchDate)}</span>
                    {m.confidence != null && <span className="text-xs text-ink-500">{m.confidence}% confidence</span>}
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={(e) => handleDelete(m.id, e)}
                    className="focus-ring p-2 rounded-lg text-ink-500 hover:text-crew-500 hover:bg-crew-500/10 transition-colors"
                    aria-label="Delete mission"
                  >
                    <Trash2 size={15} />
                  </button>
                  <ArrowUpRight size={16} className="text-ink-500 group-hover:text-judge-600 transition-colors" />
                </div>
              </GlassPanel>
            </Link>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
