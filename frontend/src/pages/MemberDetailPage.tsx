import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/endpoints";
import type { Loan, MemberDetail, Statement } from "../api/types";
import { Avatar } from "../components/Avatar";
import { DeleteButton } from "../components/DeleteButton";
import { NotificationList } from "../components/NotificationList";
import { Alert, EmptyState, ErrorMessage, Loading } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { LoanTable } from "../components/LoanTable";
import { StatCard } from "../components/StatCard";
import { StatusBadge } from "../components/StatusBadge";
import { useAction } from "../hooks/useAction";
import { useAsync } from "../hooks/useAsync";
import { formatDate, formatDateTime, MEMBER_STATUS_LABELS } from "../lib/format";
import { formatPaise } from "../lib/money";
import { EditMemberForm } from "./member-detail/EditMemberForm";
import { MemberWaitlist } from "./member-detail/MemberWaitlist";
import { PaymentForm } from "./member-detail/PaymentForm";
import { SuspensionForm } from "./member-detail/SuspensionForm";

const ACTIVE_LOAN_STATUSES = new Set<Loan["status"]>(["reserved", "checked_out", "overdue"]);
// Mirror the backend limits, used here only to colour the tiles.
const MAX_ACTIVE_LOANS = 3;
const BALANCE_LIMIT_PAISE = 10_000;

export function MemberDetailPage() {
  const memberId = Number(useParams().memberId);
  const member = useAsync(() => api.getMember(memberId), String(memberId));
  const statement = useAsync(() => api.getStatement(memberId), String(memberId));
  const [changes, setChanges] = useState(0);
  const pdf = useAction();

  const refresh = () => {
    member.reload();
    statement.reload();
    setChanges((n) => n + 1);
  };

  if (!Number.isInteger(memberId) || memberId < 1)
    return <EmptyState>Not a valid member id.</EmptyState>;
  if (member.error && !member.data)
    return <ErrorMessage error={member.error} onRetry={member.reload} />;
  if (!member.data) return <Loading rows={3} />;

  const detail = member.data;
  return (
    <section>
      <Link to="/members" className="back-link">
        <Icon name="back" size={16} /> All members
      </Link>

      <header className="hero">
        <Avatar label={detail.name} size="lg" />
        <div className="hero-main">
          <div className="hero-title">
            <h1>{detail.name}</h1>
            <StatusBadge kind="member" status={detail.status} />
          </div>
          <p className="page-sub">
            <Icon name="phone" size={14} /> {detail.phone} · Member since{" "}
            {formatDate(detail.joined_on)}
          </p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="btn btn-secondary"
            disabled={pdf.pending}
            onClick={() =>
              pdf.run(
                () => api.downloadStatementPdf(detail.id),
                () => "Statement downloaded.",
              )
            }
          >
            <Icon name="download" size={16} /> {pdf.pending ? "Preparing…" : "Statement PDF"}
          </button>
        </div>
      </header>
      {pdf.error && <ErrorMessage error={pdf.error} />}

      <div className="stat-grid stat-grid-3">
        <StatCard
          label="Fees owed"
          icon="wallet"
          tone={
            detail.fee_balance_paise > BALANCE_LIMIT_PAISE
              ? "red"
              : detail.fee_balance_paise > 0
                ? "amber"
                : "green"
          }
          value={formatPaise(detail.fee_balance_paise)}
          hint="limit ₹100"
        />
        <StatCard
          label="Active loans"
          icon="box"
          tone={detail.active_loan_count >= MAX_ACTIVE_LOANS ? "red" : "blue"}
          value={`${detail.active_loan_count} of ${MAX_ACTIVE_LOANS}`}
          hint="reserved, out or overdue"
        />
        <StatCard
          label="Fees accruing"
          icon="alarm"
          tone={statement.data?.accrued_unbilled_fees_paise ? "amber" : "grey"}
          value={statement.data ? formatPaise(statement.data.accrued_unbilled_fees_paise) : "–"}
          hint="on overdue items still out"
        />
      </div>

      <Eligibility detail={detail} />

      <div className="detail-grid detail-grid-even">
        <PaymentForm member={detail} onPaid={refresh} />
        <SuspensionForm member={detail} onChanged={refresh} />
      </div>

      <MemberWaitlist memberId={detail.id} refreshKey={String(changes)} />

      {statement.error && <ErrorMessage error={statement.error} onRetry={statement.reload} />}
      {statement.data && <StatementSections statement={statement.data} />}
      <RecentMessages memberId={detail.id} refreshKey={String(changes)} />
      <StatusHistory detail={detail} />

      <div className="detail-grid detail-grid-even">
        <EditMemberForm key={`${detail.name}|${detail.phone}`} member={detail} onSaved={refresh} />
        {statement.data &&
          statement.data.loans.length === 0 &&
          statement.data.payments.length === 0 && (
            <DeleteButton
              subject={`member ${detail.name}`}
              onDelete={() => api.deleteMember(detail.id)}
              redirectTo="/members"
            />
          )}
      </div>
    </section>
  );
}

function Eligibility({ detail }: { detail: MemberDetail }) {
  const { can_borrow, blocks } = detail.eligibility;
  if (can_borrow) {
    return <Alert tone="success" icon="userCheck" title="Can reserve and borrow items." />;
  }
  return (
    <Alert tone="warning" icon="userX" title={`Why can't ${detail.name} borrow?`}>
      <ul>
        {blocks.map((block) => (
          <li key={block.code}>{block.message}</li>
        ))}
      </ul>
    </Alert>
  );
}

function StatementSections({ statement }: { statement: Statement }) {
  const active = statement.loans.filter((loan) => ACTIVE_LOAN_STATUSES.has(loan.status));
  const past = statement.loans.filter((loan) => !ACTIVE_LOAN_STATUSES.has(loan.status));
  return (
    <>
      <div className="panel">
        <div className="panel-header">
          <h2>
            <Icon name="box" /> Active loans
          </h2>
        </div>
        {active.length ? (
          <LoanTable loans={active} hide="member" />
        ) : (
          <EmptyState icon="box">No active loans.</EmptyState>
        )}
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2>
            <Icon name="wallet" /> Statement
          </h2>
        </div>
        <div className="ledger">
          <div>
            <span>Fees charged</span>
            <strong>{formatPaise(statement.total_fees_charged_paise)}</strong>
          </div>
          <span className="ledger-op">−</span>
          <div>
            <span>Paid</span>
            <strong>{formatPaise(statement.total_paid_paise)}</strong>
          </div>
          <span className="ledger-op">=</span>
          <div className="ledger-total">
            <span>Balance</span>
            <strong>{formatPaise(statement.fee_balance_paise)}</strong>
          </div>
        </div>
        <p className="muted small">
          Late fees are added to the balance when an item comes back. Fees still accruing on overdue
          items are not part of the balance yet.
        </p>

        <h3>Payments</h3>
        {statement.payments.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Note</th>
                  <th className="num">Amount</th>
                </tr>
              </thead>
              <tbody>
                {statement.payments.map((payment) => (
                  <tr key={payment.id}>
                    <td data-label="Date">{formatDateTime(payment.paid_at)}</td>
                    <td data-label="Note">{payment.note || "—"}</td>
                    <td data-label="Amount" className="num">
                      {formatPaise(payment.amount_paise)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState icon="wallet">No payments.</EmptyState>
        )}
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2>
            <Icon name="history" /> Loan history
          </h2>
        </div>
        {past.length ? (
          <LoanTable loans={past} hide="member" />
        ) : (
          <EmptyState icon="history">No past loans.</EmptyState>
        )}
      </div>
    </>
  );
}

const RECENT_MESSAGES = 5;

function RecentMessages({ memberId, refreshKey }: { memberId: number; refreshKey: string }) {
  const messages = useAsync(
    () => api.listNotifications({ member_id: memberId, limit: RECENT_MESSAGES }),
    `${memberId}|${refreshKey}`,
  );
  if (!messages.data || messages.data.items.length === 0) return null;
  return (
    <div className="panel">
      <div className="panel-header">
        <h2>
          <Icon name="message" /> Messages sent
        </h2>
        <Link to={`/outbox?member_id=${memberId}`} className="link-more">
          All {messages.data.total} <Icon name="arrowRight" size={14} />
        </Link>
      </div>
      <NotificationList notifications={messages.data.items} showMember={false} />
    </div>
  );
}

function StatusHistory({ detail }: { detail: MemberDetail }) {
  if (!detail.status_history.length) return null;
  return (
    <div className="panel">
      <div className="panel-header">
        <h2>
          <Icon name="userX" /> Suspension history
        </h2>
      </div>
      <ul className="timeline">
        {detail.status_history.map((change) => (
          <li key={change.changed_at}>
            <span className="timeline-when">{formatDateTime(change.changed_at)}</span>
            <span>
              {MEMBER_STATUS_LABELS[change.from_status]} → {MEMBER_STATUS_LABELS[change.to_status]}
              <span className="muted"> · {change.reason}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
