import { NavLink } from "react-router-dom";
import { useEffect, useState } from "react";
import { getHealth } from "../lib/api";

const LINKS = [
  { to: "/", label: "Overview", end: true },
  { to: "/new", label: "New Session" },
  { to: "/history", label: "History" },
  { to: "/how-it-works", label: "How It Works" },
];

export default function NavBar() {
  // null = checking, true = healthy, false = unreachable or degraded
  const [online, setOnline] = useState(null);

  useEffect(() => {
    const ctrl = new AbortController();
    const check = () =>
      getHealth({ signal: ctrl.signal })
        .then((h) => setOnline(h.status === "ok"))
        .catch((e) => { if (e.name !== "AbortError") setOnline(false); });
    check();
    const t = setInterval(check, 30000);
    return () => { ctrl.abort(); clearInterval(t); };
  }, []);

  return (
    <header className="sticky top-0 z-40 px-4 pt-4">
      <div className="max-w-6xl mx-auto glass-solid rounded-2xl shadow-glass px-5 py-3 flex items-center justify-between">
        <NavLink to="/" className="flex items-center gap-2.5 shrink-0">
          <span className="relative flex h-7 w-7 items-center justify-center rounded-lg bg-judge-500 text-white font-display text-sm">
            É
          </span>
          <span className="font-display text-lg tracking-tight text-ink-900">
            ÉTOCELEST
          </span>
        </NavLink>

        <nav className="hidden md:flex items-center gap-1">
          {LINKS.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={({ isActive }) =>
                `focus-ring px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-judge-500/10 text-judge-600"
                    : "text-ink-700 hover:bg-ink-900/5"
                }`
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>

        <div className="flex items-center gap-2 text-xs text-ink-500 shrink-0">
          <span
            className={`relative flex h-2 w-2 rounded-full ${
              online ? "bg-astro-400" : online === false ? "bg-crew-500" : "bg-ink-500/40"
            }`}
          >
            {online && (
              <span className="absolute inline-flex h-full w-full rounded-full bg-astro-400 animate-pulseRing" />
            )}
          </span>
          <span className="hidden sm:inline">
            {online ? "Reasoning engine connected" : online === false ? "Server unreachable" : "Connecting..."}
          </span>
        </div>
      </div>

      <nav className="md:hidden max-w-6xl mx-auto mt-2 glass-solid rounded-xl shadow-glass flex overflow-x-auto px-2 py-1.5 gap-1">
        {LINKS.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            className={({ isActive }) =>
              `focus-ring shrink-0 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                isActive ? "bg-judge-500/10 text-judge-600" : "text-ink-700"
              }`
            }
          >
            {link.label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}
