import { useEffect, useState } from "react";
import { useParams, Link, Navigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Download, ArrowLeft, CheckCircle2, ArrowRight } from "lucide-react";
import GlassPanel from "../components/GlassPanel";
import AgentTag from "../components/AgentTag";
import { AGENTS, RESOLUTION_LABELS, getMission } from "../lib/api";

function fmtDate(iso) {
  return new Date(iso + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export default function Verdict() {
  const { sessionId } = useParams();
  const [mission, setMission] = useState(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    getMission(sessionId).then(setMission).catch(() => setNotFound(true));
  }, [sessionId]);

  if (notFound) {
    return (
      <div className="max-w-2xl mx-auto px-4 pt-24 text-center">
        <h1 className="font-display text-2xl text-ink-900 mb-3">Mission not found</h1>
        <p className="text-ink-500 mb-6">It may have been cleared, or the link is incorrect.</p>
        <Link to="/history" className="text-judge-600 font-medium">Back to history</Link>
      </div>
    );
  }

  if (!mission) {
    return (
      <div className="max-w-3xl mx-auto px-4 pt-24">
        <div className="h-6 w-2/3 bg-ink-900/5 rounded animate-pulse mb-4" />
        <div className="h-40 bg-ink-900/5 rounded-2xl animate-pulse" />
      </div>
    );
  }

  if (mission.status !== "complete") {
    return <Navigate to={`/debate/${mission.id}`} replace />;
  }

  const g = mission.grounding;
  const dateChanged = mission.recommendedDate && mission.recommendedDate !== mission.launchDate;

  const handleExport = () => {
    const blob = new Blob([JSON.stringify(mission, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `etocelest-${mission.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="max-w-3xl mx-auto px-4 pt-10 pb-24">
      <Link to="/history" className="focus-ring inline-flex items-center gap-1.5 text-sm text-ink-500 hover:text-ink-900 mb-6 transition-colors">
        <ArrowLeft size={14} /> All missions
      </Link>

      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
        <p className="text-xs font-mono text-ink-500 mb-2">mission_{mission.id}</p>
        <h1 className="font-display text-3xl text-ink-900 mb-3 leading-snug">{mission.name}</h1>
        <div className="flex items-center gap-2 text-sm font-mono mb-6">
          <span className={dateChanged ? "line-through text-ink-500/60" : "text-ink-700"}>{fmtDate(mission.launchDate)}</span>
          {dateChanged && (
            <>
              <ArrowRight size={14} className="text-judge-500" />
              <span className="text-judge-600 font-medium">{fmtDate(mission.recommendedDate)}</span>
            </>
          )}
        </div>
      </motion.div>

      <GlassPanel className="p-7 mb-6" solid>
        <div className="flex items-center gap-2 mb-4">
          <CheckCircle2 size={18} className="text-astro-500" />
          <span className="text-sm font-medium text-ink-500">Ruling issued</span>
        </div>
        <h2 className="font-display text-3xl text-ink-900 mb-3">{mission.verdict}</h2>
        <p className="text-ink-700 leading-relaxed mb-6">{mission.verdictSummary}</p>

        {mission.resolution && (
          <p className="text-xs font-mono text-ink-500 mb-4">
            Resolution: {RESOLUTION_LABELS[mission.resolution] || mission.resolution}
          </p>
        )}
        <div className="grid sm:grid-cols-3 gap-4">
          <div className="rounded-xl bg-ink-900/5 px-4 py-3">
            <p className="text-xs text-ink-500 mb-1">Confidence</p>
            <p className="font-display text-2xl text-ink-900">{mission.confidence}%</p>
          </div>
          <div className="rounded-xl bg-ink-900/5 px-4 py-3">
            <p className="text-xs text-ink-500 mb-1">Debate rounds</p>
            <p className="font-display text-2xl text-ink-900">{mission.roundsCompleted}</p>
          </div>
          <div className="rounded-xl bg-ink-900/5 px-4 py-3">
            <p className="text-xs text-ink-500 mb-1">Filed</p>
            <p className="font-display text-2xl text-ink-900">
              {new Date(mission.createdAt).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
            </p>
          </div>
        </div>
      </GlassPanel>

      {g && (
        <GlassPanel className="p-7 mb-6">
          <h3 className="font-display text-xl text-ink-900 mb-3">Data sources</h3>
          {g.available ? (
            <p className="text-sm text-ink-700 leading-relaxed">
              {g.source}, launch month {g.launchMonth} (sunspot number{" "}
              {g.months.find((m) => m.isLaunchMonth)?.ssn}, F10.7 {g.months.find((m) => m.isLaunchMonth)?.f107}).
              Monthly statistical predictions, not forecasts of individual flares or CMEs.
            </p>
          ) : (
            <p className="text-sm text-ink-700 leading-relaxed">
              No external solar-activity data was used: {g.reason}. Agents were instructed not to cite solar figures.
            </p>
          )}
        </GlassPanel>
      )}

      {mission.rounds?.length > 0 && (
        <GlassPanel className="p-7 mb-6">
          <h3 className="font-display text-xl text-ink-900 mb-5">Reasoning trace</h3>
          <div className="space-y-6">
            {mission.rounds.map((rd) => (
              <div key={rd.round}>
                <p className="text-xs font-mono font-medium text-ink-500 bg-ink-900/5 inline-block px-2.5 py-1 rounded-full mb-3">
                  Round {rd.round}
                </p>
                <div className="space-y-3">
                  {rd.turns.map((t, i) => (
                    <div key={i} className="flex gap-3">
                      <AgentTag agent={t.agent} label={AGENTS[t.agent]?.name || t.agent} size="sm" />
                      <div className="flex-1">
                        <p className={`text-sm leading-relaxed ${t.failed ? "text-ink-500 italic" : "text-ink-700"}`}>{t.text}</p>
                        {!t.failed && t.proposedShiftDays !== undefined && (
                          <p className="mt-1 text-xs font-mono text-ink-500">
                            proposes +{t.proposedShiftDays}d · accepts +{t.acceptableMinDays}–{t.acceptableMaxDays}d{t.hardConstraint ? " · hard limit" : ""}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                  {rd.judge && (
                    <p className="text-sm text-ink-500 pl-1 italic">
                      Judge: {rd.judge.resolved ? "ruled — " : "reopened — "}
                      {rd.judge.note}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </GlassPanel>
      )}

      <button
        onClick={handleExport}
        className="focus-ring inline-flex items-center gap-2 bg-white/70 hover:bg-white border border-ink-900/10 text-ink-900 font-medium px-5 py-3 rounded-xl transition-colors"
      >
        <Download size={16} /> Export as JSON
      </button>
    </div>
  );
}
