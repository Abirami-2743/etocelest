import { useEffect, useState } from "react";
import { getHealth } from "../lib/api";

export default function Footer() {
  const [health, setHealth] = useState(null);

  useEffect(() => {
    const ctrl = new AbortController();
    getHealth({ signal: ctrl.signal }).then(setHealth).catch(() => {});
    return () => ctrl.abort();
  }, []);

  return (
    <footer className="mt-24 px-4 pb-8">
      <div className="max-w-6xl mx-auto glass rounded-2xl px-6 py-6 flex flex-col sm:flex-row items-center justify-between gap-3 text-sm text-ink-500">
        <p>ÉTOCELEST — adversarial reasoning for decisions that need a paper trail.</p>
        {health && (
          <p className="font-mono text-xs">
            v{health.version} · {health.llm.agentModel}
          </p>
        )}
      </div>
    </footer>
  );
}
