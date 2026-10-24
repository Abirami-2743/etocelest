import { Scale, Sun, Fuel, Users, Sparkles } from "lucide-react";

const ICONS = {
  astro: Sun,
  logistics: Fuel,
  crew: Users,
  missionvalue: Sparkles,
  judge: Scale,
};

const STYLES = {
  astro: "bg-astro-500/10 text-astro-500 ring-astro-500/25",
  logistics: "bg-logistics-500/10 text-logistics-500 ring-logistics-500/25",
  crew: "bg-crew-500/10 text-crew-500 ring-crew-500/25",
  missionvalue: "bg-missionvalue-500/10 text-missionvalue-500 ring-missionvalue-500/25",
  judge: "bg-judge-500/10 text-judge-600 ring-judge-500/25",
};

const DOT = {
  astro: "bg-astro-400",
  logistics: "bg-logistics-400",
  crew: "bg-crew-400",
  missionvalue: "bg-missionvalue-400",
  judge: "bg-judge-500",
};

export function AgentDot({ agent, size = "sm" }) {
  return <span className={`inline-block rounded-full ${DOT[agent]} ${size === "sm" ? "w-2 h-2" : "w-3 h-3"}`} />;
}

export default function AgentTag({ agent, label, size = "md" }) {
  const Icon = ICONS[agent] || Scale;
  const padding = size === "sm" ? "px-2.5 py-1 text-xs" : "px-3 py-1.5 text-sm";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full ring-1 font-medium whitespace-nowrap ${STYLES[agent]} ${padding}`}
    >
      <Icon size={size === "sm" ? 12 : 14} strokeWidth={2.4} />
      {label}
    </span>
  );
}
