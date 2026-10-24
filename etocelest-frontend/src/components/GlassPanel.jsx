export default function GlassPanel({ as: Tag = "div", className = "", solid = false, ...props }) {
  return (
    <Tag
      className={`${solid ? "glass-solid" : "glass"} rounded-2xl shadow-glass ${className}`}
      {...props}
    />
  );
}
