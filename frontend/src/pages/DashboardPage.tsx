import { Link } from "react-router-dom";
import { api } from "../api/endpoints";
import { Avatar } from "../components/Avatar";
import { EmptyState, ErrorMessage, Loading } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { OverdueSeverity } from "../components/OverdueSeverity";
import { StatCard } from "../components/StatCard";
import { useAsync } from "../hooks/useAsync";
import { useClock } from "../hooks/useClock";
import { useStatusCounts } from "../hooks/useStatusCounts";
import { formatDateTime, formatRelative } from "../lib/format";
import { formatPaise } from "../lib/money";

const ATTENTION_LIMIT = 5;

export function DashboardPage() {
  const { override } = useClock();
  const nowMs = override ? new Date(override).getTime() : Date.now();
  const counts = useStatusCounts();
  const overdue = useAsync(() => api.listOverdue(0), "dashboard");
  const reserved = useAsync(() => api.listItems({ status: "reserved", limit: 50 }), "dashboard");

  const accruing = overdue.data?.items.reduce((sum, loan) => sum + loan.accrued_fee_paise, 0) ?? 0;
  const holds = (reserved.data?.items ?? [])
    .filter((item) => item.current_loan)
    .sort((a, b) =>
      a.current_loan!.reservation_expires_at.localeCompare(b.current_loan!.reservation_expires_at),
    );

  return (
    <section>
      <header className="page-header">
        <div>
          <h1>Dashboard</h1>
          <p className="page-sub">What needs the desk's attention right now.</p>
        </div>
        <div className="page-actions">
          <Link to="/items" className="btn btn-secondary">
            <Icon name="tool" size={16} /> Browse items
          </Link>
          <Link to="/members" className="btn btn-primary">
            <Icon name="users" size={16} /> Find a member
          </Link>
        </div>
      </header>

      {counts.error && <ErrorMessage error={counts.error} onRetry={counts.reload} />}
      <div className="stat-grid">
        <StatCard
          label="Available"
          icon="check"
          tone="green"
          to="/items?status=available"
          value={counts.data?.available ?? "–"}
          hint="ready to lend"
        />
        <StatCard
          label="Reserved"
          icon="hand"
          tone="blue"
          to="/items?status=reserved"
          value={counts.data?.reserved ?? "–"}
          hint="48-hour holds"
        />
        <StatCard
          label="Checked out"
          icon="box"
          tone="amber"
          to="/items?status=checked_out"
          value={counts.data?.checked_out ?? "–"}
          hint="on time"
        />
        <StatCard
          label="Overdue"
          icon="alarm"
          tone="red"
          to="/overdue"
          value={counts.data?.overdue ?? "–"}
          hint={`${formatPaise(accruing)} in fees accruing`}
        />
        <StatCard
          label="Maintenance"
          icon="wrench"
          tone="grey"
          to="/items?status=maintenance"
          value={counts.data?.maintenance ?? "–"}
          hint="out of service"
        />
      </div>

      <div className="dashboard-grid">
        <div className="panel">
          <div className="panel-header">
            <h2>
              <Icon name="alarm" /> Overdue loans
            </h2>
            <Link to="/overdue" className="link-more">
              View all <Icon name="arrowRight" size={14} />
            </Link>
          </div>
          {overdue.error && <ErrorMessage error={overdue.error} onRetry={overdue.reload} />}
          {overdue.loading && !overdue.data && <Loading rows={3} />}
          {overdue.data && overdue.data.items.length === 0 && (
            <EmptyState icon="check">Nothing is overdue. Nice.</EmptyState>
          )}
          <ul className="list">
            {overdue.data?.items.slice(0, ATTENTION_LIMIT).map((loan) => (
              <li key={loan.id} className="list-row">
                <Avatar label={loan.member_name} />
                <div className="list-main">
                  <Link to={`/items/${loan.item_id}`} className="list-title">
                    {loan.item_name}
                  </Link>
                  <span className="list-sub">
                    <Link to={`/members/${loan.member_id}`}>{loan.member_name}</Link> ·{" "}
                    {loan.member_phone}
                  </span>
                </div>
                <div className="list-side">
                  <OverdueSeverity days={loan.days_overdue} />
                  <span className="list-sub">{formatPaise(loan.accrued_fee_paise)} so far</span>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="panel">
          <div className="panel-header">
            <h2>
              <Icon name="hand" /> Waiting for pickup
            </h2>
            <Link to="/items?status=reserved" className="link-more">
              View all <Icon name="arrowRight" size={14} />
            </Link>
          </div>
          {reserved.error && <ErrorMessage error={reserved.error} onRetry={reserved.reload} />}
          {reserved.loading && !reserved.data && <Loading rows={3} />}
          {reserved.data && holds.length === 0 && (
            <EmptyState icon="hand">No reservations waiting.</EmptyState>
          )}
          <ul className="list">
            {holds.slice(0, ATTENTION_LIMIT).map((item) => {
              const loan = item.current_loan!;
              const soon = new Date(loan.reservation_expires_at).getTime() - nowMs < 6 * 3_600_000;
              return (
                <li key={item.id} className="list-row">
                  <Avatar label={item.name} colorKey={item.category} />
                  <div className="list-main">
                    <Link to={`/items/${item.id}`} className="list-title">
                      {item.name}
                    </Link>
                    <span className="list-sub">for {loan.member_name}</span>
                  </div>
                  <div className="list-side">
                    <span className={`chip ${soon ? "tone-amber" : "tone-blue"}`}>
                      <Icon name="clock" size={13} /> expires{" "}
                      {formatRelative(loan.reservation_expires_at, nowMs)}
                    </span>
                    <span className="list-sub">{formatDateTime(loan.reservation_expires_at)}</span>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </section>
  );
}
