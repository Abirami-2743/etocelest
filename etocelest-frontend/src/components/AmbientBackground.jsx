export default function AmbientBackground() {
  return (
    <div className="fixed inset-0 -z-10 overflow-hidden bg-canvas-100">
      <div className="absolute -top-32 -left-24 h-[28rem] w-[28rem] rounded-full bg-judge-500/10 blur-3xl animate-drift" />
      <div className="absolute top-1/3 -right-32 h-[26rem] w-[26rem] rounded-full bg-astro-400/10 blur-3xl animate-drift-slow" />
      <div className="absolute bottom-0 left-1/4 h-[24rem] w-[24rem] rounded-full bg-crew-400/10 blur-3xl animate-drift" />
      <div className="absolute inset-0 bg-grain" />
    </div>
  );
}
