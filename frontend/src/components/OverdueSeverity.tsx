// Mirrors the backend rule: more than 14 days overdue blocks the member from borrowing.
export const BLOCKING_DAYS_OVERDUE = 14;

/** A bar that fills as a loan approaches the 14-day borrowing block. */
export function OverdueSeverity({ days }: { days: number }) {
  const blocked = days > BLOCKING_DAYS_OVERDUE;
  const percent = Math.min(100, Math.round((days / (BLOCKING_DAYS_OVERDUE + 1)) * 100));
  return (
    <span className={`severity ${blocked ? "severity-blocked" : ""}`}>
      <span className="severity-text">
        {days} {days === 1 ? "day" : "days"} late{blocked && " · member blocked"}
      </span>
      <span className="severity-track">
        <span className="severity-fill" style={{ width: `${percent}%` }} />
      </span>
    </span>
  );
}
