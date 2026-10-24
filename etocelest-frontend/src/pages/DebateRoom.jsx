import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2, ArrowRight, Scale, CircleCheck, CircleAlert, TriangleAlert, RotateCw } from "lucide-react";
import GlassPanel from "../components/GlassPanel";
import AgentTag, { AgentDot } from "../components/AgentTag";
import { AGENTS, RESOLUTION_LABELS, getMission, retryMission, runMissionDebate } from "../lib/api";

function fmtDate(iso) {
  return new Date(iso + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

const upd = (rounds, n, fn) => rounds.map((rd) => (rd.round === n ? fn(rd) : rd));

function verdictFrom(src) {
  return {
    verdict: src.verdict,
    summary: src.verdictSummary,
    confidence: src.confidence,
    recommendedDate: src.recommendedDate,
    resolution: src.resolution,
  };
}

export default function DebateRoom() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [mission, setMission] = useState(null);
  const [status, setStatus] = useState("Connecting to reasoning engine...");
  const [rounds, setRounds] = useState([]);
  const [typing, setTyping] = useState(null);
  const [finalVerdict, setFinalVerdict] = useState(null);
  const [done, setDone] = useState(false);
  const [error, setError] = useState(null);
  const [attempt, setAttempt] = useState(0);
  const scrollRef = useRef(null);

  useEffect(() => {
    const ctrl = new AbortController();
    const live = () => !ctrl.signal.aborted;

    // Every (re)start rebuilds state from the server: the stream replays persisted events first.
    setRounds([]);
    setTyping(null);
    setFinalVerdict(null);
    setDone(false);
    setError(null);
    setStatus("Connecting to reasoning engine...");

    (async () => {
      try {
        const m = await getMission(sessionId);
        if (!live()) return;
        setMission(m);

        if (m.status === "failed") {
          setStatus(null);
          setError(m.error || "The review failed.");
          return;
        }

        await runMissionDebate(
          sessionId,
          (evt) => {
            if (!live()) return;
            switch (evt.type) {
              case "status":
                setStatus(evt.value);
                break;
              case "round_start":
                setStatus(null);
                setRounds((r) => [...r, { round: evt.round, turns: [], judge: null, judgeStatus: "debating" }]);
                break;
              case "turn_start":
                setTyping({ round: evt.round, agent: evt.agent });
                break;
              case "turn_text":
              case "turn_failed":
                setTyping(null);
                setRounds((r) =>
                  upd(r, evt.round, (rd) => ({
                    ...rd,
                    turns: [
                      ...rd.turns,
                      {
                        agent: evt.agent,
                        text: evt.text,
                        failed: evt.type === "turn_failed",
                        proposedShiftDays: evt.proposedShiftDays,
                        acceptableMinDays: evt.acceptableMinDays,
                        acceptableMaxDays: evt.acceptableMaxDays,
                        hardConstraint: evt.hardConstraint,
                      },
                    ],
                  }))
                );
                break;
              case "judge_evaluating":
                setTyping(null);
                setRounds((r) => upd(r, evt.round, (rd) => ({ ...rd, judgeStatus: "evaluating" })));
                break;
              case "judge_note":
                setRounds((r) =>
                  upd(r, evt.round, (rd) => ({
                    ...rd,
                    judgeStatus: "done",
                    judge: { resolved: evt.resolved, note: evt.note, openIssues: evt.openIssues || [] },
                  }))
                );
                if (evt.resolved) setFinalVerdict(verdictFrom(evt));
                break;
              case "done":
                setStatus(null);
                setDone(true);
                break;
              case "error":
                setStatus(null);
                setTyping(null);
                setError(evt.message || "The review failed.");
                break;
              default:
                break;
            }
          },
          { signal: ctrl.signal }
        );
      } catch (err) {
        if (!live() || err.name === "AbortError") return;
        setStatus(null);
        setTyping(null);
        setError(err.message || "Something went wrong.");
      }
    })();

    return () => ctrl.abort();
  }, [sessionId, attempt]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [rounds, status, typing]);

  const handleRetry = useCallback(async () => {
    try {
      await retryMission(sessionId);
      setAttempt((a) => a + 1);
    } catch (err) {
      setError(err.message);
    }
  }, [sessionId]);

  const dateChanged = finalVerdict && mission && finalVerdict.recommendedDate !== mission.launchDate;
  const latest = rounds[rounds.length - 1];
  const positions = latest ? latest.turns.filter((t) => !t.failed && t.proposedShiftDays !== undefined) : [];
  const maxRounds = mission?.limits?.maxRounds;

  return (
    <div className="max-w-4xl mx-auto px-4 pt-10 pb-24">
      <div className="mb-6">
        <p className="text-xs font-mono text-ink-500 mb-2">mission_{sessionId}</p>
        <h1 className="font-display text-2xl sm:text-3xl text-ink-900 leading-snug mb-3">
          {mission?.name || "Loading mission..."}
        </h1>
        {mission && (
          <div className="flex items-center gap-2 text-sm font-mono">
            <span className={dateChanged ? "line-through text-ink-500/60" : "text-ink-700"}>{fmtDate(mission.launchDate)}</span>
            {dateChanged && (
              <>
                <ArrowRight size={14} className="text-judge-500" />
                <span className="text-judge-600 font-medium">{fmtDate(finalVerdict.recommendedDate)}</span>
              </>
            )}
          </div>
        )}
      </div>

      <GlassPanel className="p-0 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-ink-900/5 bg-white/40 flex-wrap gap-2">
          <div className="flex items-center gap-3 flex-wrap">
            {Object.values(AGENTS).filter((a) => a.id !== "judge").map((a) => (
              <span key={a.id} className="flex items-center gap-1.5 text-xs text-ink-500">
                <AgentDot agent={a.id} /> {a.name}
              </span>
            ))}
          </div>
          <span className="text-xs font-mono text-ink-500">
            {error ? "stopped" : done ? "closed" : maxRounds && latest ? `live · round ${latest.round}/${maxRounds}` : "live"}
          </span>
        </div>

        <div ref={scrollRef} className="max-h-[32rem] overflow-y-auto px-5 py-6 space-y-7" aria-live="polite">
          <AnimatePresence initial={false}>
            {rounds.map((rd) => (
              <motion.div key={rd.round} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
                <div className="flex items-center gap-2 mb-4">
                  <span className="text-xs font-mono font-medium text-ink-500 bg-ink-900/5 px-2.5 py-1 rounded-full">Round {rd.round}</span>
                  <div className="flex-1 h-px bg-ink-900/5" />
                </div>

                <div className="space-y-4">
                  {rd.turns.map((turn, i) => {
                    const agent = AGENTS[turn.agent];
                    return (
                      <motion.div key={i} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3">
                        <div className="pt-0.5">
                          <AgentTag agent={agent.id} label={agent.name} size="sm" />
                        </div>
                        <div className="flex-1 pt-0.5">
                          <p className={`text-sm sm:text-base leading-relaxed ${turn.failed ? "text-ink-500 italic" : "text-ink-700"}`}>
                            {turn.text}
                          </p>
                          {!turn.failed && turn.proposedShiftDays !== undefined && (
                            <p className="mt-1.5 text-xs font-mono text-ink-500">
                              proposes +{turn.proposedShiftDays}d · accepts +{turn.acceptableMinDays}–{turn.acceptableMaxDays}d
                              {turn.hardConstraint ? " · hard limit" : ""}
                            </p>
                          )}
                        </div>
                      </motion.div>
                    );
                  })}

                  {typing && typing.round === rd.round && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-2">
                      <AgentTag agent={typing.agent} label={`${AGENTS[typing.agent].name} is composing...`} size="sm" />
                    </motion.div>
                  )}

                  {rd.judgeStatus === "evaluating" && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-2.5 text-sm text-ink-500 font-mono pl-1">
                      <Loader2 size={14} className="animate-spin" /> Judge reviewing round {rd.round}...
                    </motion.div>
                  )}

                  {rd.judge && (
                    <motion.div
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      className={`flex gap-3 rounded-xl px-4 py-3 ${rd.judge.resolved ? "bg-judge-500/5" : "bg-ink-900/5"}`}
                    >
                      {rd.judge.resolved ? (
                        <CircleCheck size={16} className="text-judge-500 shrink-0 mt-0.5" />
                      ) : (
                        <CircleAlert size={16} className="text-ink-500 shrink-0 mt-0.5" />
                      )}
                      <div className="text-sm text-ink-700 leading-relaxed">
                        <p>
                          <span className="font-medium text-ink-900">
                            {rd.judge.resolved ? "Judge: ruling issued. " : "Judge: sending back for another round. "}
                          </span>
                          {rd.judge.note}
                        </p>
                        {rd.judge.openIssues.length > 0 && (
                          <ul className="mt-2 space-y-1">
                            {rd.judge.openIssues.map((q, i) => (
                              <li key={i} className="text-ink-500">
                                <span className="font-medium text-ink-700">
                                  {q.agent === "all" ? "All agents" : AGENTS[q.agent]?.name}:
                                </span>{" "}
                                {q.question}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    </motion.div>
                  )}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>

          {status && !done && !error && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-2.5 text-sm text-ink-500 font-mono">
              <Loader2 size={14} className="animate-spin" /> {status}
            </motion.div>
          )}
        </div>
      </GlassPanel>

      {error && (
        <GlassPanel className="mt-6 p-5" solid>
          <div className="flex items-start gap-3">
            <TriangleAlert size={18} className="text-crew-500 shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="font-medium text-ink-900 mb-1">The review stopped</p>
              <p className="text-sm text-ink-700 mb-4">{error}</p>
              <button
                onClick={handleRetry}
                className="focus-ring inline-flex items-center gap-2 bg-judge-500 hover:bg-judge-600 transition-colors text-white text-sm font-medium px-4 py-2 rounded-lg"
              >
                <RotateCw size={14} /> Retry from the last completed round
              </button>
            </div>
          </div>
        </GlassPanel>
      )}

      <AnimatePresence>
        {finalVerdict && (
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} className="mt-6">
            <GlassPanel className="p-6" solid>
              <div className="flex items-center gap-2 mb-3 flex-wrap">
                <AgentTag agent="judge" label="Judge's ruling" />
                {finalVerdict.resolution && (
                  <span className="text-xs font-mono text-ink-500 bg-ink-900/5 px-2.5 py-1 rounded-full">
                    {RESOLUTION_LABELS[finalVerdict.resolution] || finalVerdict.resolution}
                  </span>
                )}
              </div>
              <h2 className="font-display text-2xl text-ink-900 mb-2">{finalVerdict.verdict}</h2>
              <p className="text-ink-700 leading-relaxed mb-5">{finalVerdict.summary}</p>
              <div className="flex items-center gap-3 mb-6">
                <span className="text-xs text-ink-500 font-mono w-20">Confidence</span>
                <div className="flex-1 h-2 rounded-full bg-ink-900/5 overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${finalVerdict.confidence}%` }}
                    transition={{ duration: 0.9, ease: "easeOut" }}
                    className="h-full rounded-full bg-gradient-to-r from-judge-500 to-astro-400"
                  />
                </div>
                <span className="text-sm font-medium text-ink-900 w-10 text-right">{finalVerdict.confidence}%</span>
              </div>
              {done && (
                <button
                  onClick={() => navigate(`/verdict/${sessionId}`)}
                  className="focus-ring inline-flex items-center gap-2 text-judge-600 font-medium hover:gap-3 transition-all"
                >
                  View full verdict report <ArrowRight size={16} />
                </button>
              )}
            </GlassPanel>
          </motion.div>
        )}
      </AnimatePresence>

      {positions.length > 0 && (
        <GlassPanel className="mt-6 p-5">
          <div className="flex items-center gap-2 mb-4">
            <Scale size={14} className="text-ink-500" />
            <p className="text-xs font-medium text-ink-500">
              Stated positions, round {latest.round} (days of delay each agent proposes and accepts)
            </p>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {positions.map((t) => (
              <div key={t.agent} className="rounded-lg bg-ink-900/5 px-3 py-2.5">
                <span className="text-xs text-ink-700">{AGENTS[t.agent].name}</span>
                <p className="font-display text-xl text-ink-900 mt-0.5">+{t.proposedShiftDays}d</p>
                <p className="text-xs font-mono text-ink-500">
                  accepts +{t.acceptableMinDays}–{t.acceptableMaxDays}d{t.hardConstraint ? " · hard" : ""}
                </p>
              </div>
            ))}
          </div>
        </GlassPanel>
      )}
    </div>
  );
}
