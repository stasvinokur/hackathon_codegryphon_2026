interface StatCardProps {
  label: string;
  value: string | number;
  tone?: "default" | "danger" | "success";
  onClick?: () => void;
}

export function StatCard({ label, value, tone = "default", onClick }: StatCardProps): JSX.Element {
  return (
    <article
      className={`stat-card stat-card--${tone}`}
      onClick={onClick}
      style={{ cursor: onClick ? "pointer" : undefined }}
    >
      <p className="stat-card__label">{label}</p>
      <p className="stat-card__value">{value}</p>
    </article>
  );
}
