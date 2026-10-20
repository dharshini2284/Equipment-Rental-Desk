import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/endpoints";
import { Avatar } from "../components/Avatar";
import { EmptyState, ErrorMessage, Loading } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { BLOCKING_DAYS_OVERDUE, OverdueSeverity } from "../components/OverdueSeverity";
import { Pagination } from "../components/Pagination";
import { StatCard } from "../components/StatCard";
import { useAsync } from "../hooks/useAsync";
import { formatDateTime } from "../lib/format";
import { formatPaise } from "../lib/money";

export function OverduePage() {
  const [offset, setOffset] = useState(0);
  const overdue = useAsync(() => api.listOverdue(offset), String(offset));

  const loans = overdue.data?.items ?? [];
  const accruing = loans.reduce((sum, loan) => sum + loan.accrued_fee_paise, 0);
  const blocking = loans.filter((loan) => loan.days_overdue > BLOCKING_DAYS_OVERDUE).length;

  return (
    <section>
      <header className="page-header">
        <div>
          <h1>Overdue</h1>
          <p className="page-sub">Loans past their due time, most overdue first.</p>
        </div>
      </header>

      <div className="stat-grid stat-grid-3">
        <StatCard
          label="Overdue loans"
          icon="alarm"
          tone="red"
          value={overdue.data?.total ?? "–"}
        />
        <StatCard
          label="Fees accruing"
          icon="wallet"
          tone="amber"
          value={overdue.data ? formatPaise(accruing) : "–"}
          hint="charged when each item comes back"
        />
        <StatCard
          label="Members blocked"
          icon="userX"
          tone="grey"
          value={overdue.data ? blocking : "–"}
          hint={`loans more than ${BLOCKING_DAYS_OVERDUE} days late`}
        />
      </div>

      {overdue.error && <ErrorMessage error={overdue.error} onRetry={overdue.reload} />}
      {overdue.loading && !overdue.data && <Loading rows={4} />}
      {overdue.data && loans.length === 0 && (
        <EmptyState icon="check">Nothing is overdue.</EmptyState>
      )}
      {loans.length > 0 && (
        <div className="panel panel-flush">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Member</th>
                  <th>Due</th>
                  <th>Lateness</th>
                  <th className="num">Fee so far</th>
                </tr>
              </thead>
              <tbody>
                {loans.map((loan) => (
                  <tr
                    key={loan.id}
                    className={loan.days_overdue > BLOCKING_DAYS_OVERDUE ? "row-alert" : ""}
                  >
                    <td data-label="Item">
                      <Link to={`/items/${loan.item_id}`} className="strong-link">
                        {loan.item_name}
                      </Link>
                    </td>
                    <td data-label="Member">
                      <span className="cell-person">
                        <Avatar label={loan.member_name} size="sm" />
                        <span>
                          <Link to={`/members/${loan.member_id}`}>{loan.member_name}</Link>
                          <a className="list-sub" href={`tel:${loan.member_phone}`}>
                            <Icon name="phone" size={12} /> {loan.member_phone}
                          </a>
                        </span>
                      </span>
                    </td>
                    <td data-label="Due">{formatDateTime(loan.due_at)}</td>
                    <td data-label="Lateness">
                      <OverdueSeverity days={loan.days_overdue} />
                    </td>
                    <td data-label="Fee so far" className="num">
                      <strong>{formatPaise(loan.accrued_fee_paise)}</strong>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {overdue.data && (
        <Pagination
          total={overdue.data.total}
          limit={overdue.data.limit}
          offset={overdue.data.offset}
          onChange={setOffset}
        />
      )}
    </section>
  );
}
