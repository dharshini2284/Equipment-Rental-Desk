import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Icon, type IconName } from "./Icon";

export type Tone = "green" | "blue" | "amber" | "red" | "grey" | "brand";

interface Props {
  label: string;
  value: ReactNode;
  icon: IconName;
  tone: Tone;
  hint?: string;
  to?: string;
}

export function StatCard({ label, value, icon, tone, hint, to }: Props) {
  const body = (
    <>
      <span className={`stat-icon tone-${tone}`}>
        <Icon name={icon} size={20} />
      </span>
      <span className="stat-text">
        <span className="stat-label">{label}</span>
        <span className="stat-value">{value}</span>
        {hint && <span className="stat-hint">{hint}</span>}
      </span>
    </>
  );
  return to ? (
    <Link to={to} className="stat-card stat-card-link">
      {body}
    </Link>
  ) : (
    <div className="stat-card">{body}</div>
  );
}
