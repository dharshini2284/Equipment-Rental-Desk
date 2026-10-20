import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/endpoints";
import type { Item, Loan } from "../api/types";
import { Avatar } from "../components/Avatar";
import { DeleteButton } from "../components/DeleteButton";
import { EmptyState, ErrorMessage, Loading } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { LoanTable } from "../components/LoanTable";
import { StatusBadge } from "../components/StatusBadge";
import { useAsync } from "../hooks/useAsync";
import { formatDateTime } from "../lib/format";
import { formatPaise } from "../lib/money";
import { EditItemForm } from "./item-detail/EditItemForm";
import { ItemActions } from "./item-detail/ItemActions";
import { WaitlistPanel } from "./item-detail/WaitlistPanel";

export function ItemDetailPage() {
  const itemId = Number(useParams().itemId);
  const item = useAsync(() => api.getItem(itemId), String(itemId));
  const history = useAsync(() => api.listLoans({ item_id: itemId }), String(itemId));

  const [changes, setChanges] = useState(0);

  const refresh = () => {
    item.reload();
    history.reload();
    setChanges((n) => n + 1);
  };

  if (!Number.isInteger(itemId) || itemId < 1) return <EmptyState>Not a valid item id.</EmptyState>;
  if (item.error && !item.data) return <ErrorMessage error={item.error} onRetry={item.reload} />;
  if (!item.data) return <Loading rows={3} />;

  const current = item.data;
  return (
    <section>
      <Link to="/items" className="back-link">
        <Icon name="back" size={16} /> All items
      </Link>

      <header className="hero">
        <Avatar label={current.name} colorKey={current.category} size="lg" />
        <div className="hero-main">
          <div className="hero-title">
            <h1>{current.name}</h1>
            <StatusBadge kind="item" status={current.status} />
          </div>
          <p className="page-sub">
            {current.category} · Replacement value {formatPaise(current.replacement_value_paise)}
          </p>
        </div>
      </header>
      {item.error && <ErrorMessage error={item.error} onRetry={item.reload} />}

      <Lifecycle item={current} />

      <div className="detail-grid">
        <div className="detail-main">
          {current.current_loan && <CurrentLoan loan={current.current_loan} />}
          <ItemActions item={current} onChanged={refresh} />
          <WaitlistPanel item={current} refreshKey={String(changes)} onChanged={refresh} />
        </div>
        <aside className="detail-side">
          <div className="panel">
            <h2>Details</h2>
            <dl className="kv">
              <dt>Category</dt>
              <dd>{current.category}</dd>
              <dt>Replacement value</dt>
              <dd>{formatPaise(current.replacement_value_paise)}</dd>
              <dt>Condition</dt>
              <dd>{current.condition_note || <span className="muted">No notes</span>}</dd>
              <dt>Last change</dt>
              <dd>{formatDateTime(current.updated_at)}</dd>
            </dl>
          </div>
          <EditItemForm key={current.updated_at} item={current} onSaved={item.reload} />
          {history.data?.total === 0 && (
            <DeleteButton
              subject={`item “${current.name}”`}
              onDelete={() => api.deleteItem(current.id)}
              redirectTo="/items"
            />
          )}
        </aside>
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2>
            <Icon name="history" /> Loan history
          </h2>
        </div>
        {history.error && <ErrorMessage error={history.error} onRetry={history.reload} />}
        {history.data && history.data.items.length === 0 && (
          <EmptyState icon="history">This item has never been borrowed.</EmptyState>
        )}
        {history.data && history.data.items.length > 0 && (
          <LoanTable loans={history.data.items} hide="item" />
        )}
      </div>
    </section>
  );
}

const STEPS = ["Available", "Reserved", "Checked out", "Returned"] as const;

/** Where the item is in the lending cycle; overdue is shown as a late "checked out" step. */
function Lifecycle({ item }: { item: Item }) {
  if (item.status === "maintenance") {
    return (
      <div className="lifecycle lifecycle-maintenance">
        <Icon name="wrench" /> Out of service for maintenance. Return it to service to lend it
        again.
      </div>
    );
  }
  const position =
    item.status === "reserved"
      ? 1
      : item.status === "checked_out" || item.status === "overdue"
        ? 2
        : 0;
  return (
    <ol className="lifecycle" aria-label="Lending cycle">
      {STEPS.map((step, index) => {
        const state = index < position ? "done" : index === position ? "current" : "todo";
        const late = index === 2 && item.status === "overdue";
        return (
          <li key={step} className={`step step-${state} ${late ? "step-late" : ""}`}>
            <span className="step-dot">
              {state === "done" ? <Icon name="check" size={14} /> : index + 1}
            </span>
            <span className="step-label">{late ? "Overdue" : step}</span>
          </li>
        );
      })}
    </ol>
  );
}

function CurrentLoan({ loan }: { loan: Loan }) {
  const overdue = loan.status === "overdue";
  return (
    <div className={`panel loan-card ${overdue ? "loan-card-late" : ""}`}>
      <div className="panel-header">
        <h2>Current loan #{loan.id}</h2>
        <StatusBadge kind="loan" status={loan.status} />
      </div>
      <div className="loan-person">
        <Avatar label={loan.member_name} />
        <div>
          <Link to={`/members/${loan.member_id}`} className="list-title">
            {loan.member_name}
          </Link>
          <span className="list-sub">
            <Icon name="phone" size={13} /> {loan.member_phone}
          </span>
        </div>
      </div>
      <dl className="kv kv-inline">
        {loan.status === "reserved" ? (
          <>
            <dt>Reserved</dt>
            <dd>{formatDateTime(loan.reserved_at)}</dd>
            <dt>Hold ends</dt>
            <dd>
              <strong>{formatDateTime(loan.reservation_expires_at)}</strong>
            </dd>
          </>
        ) : (
          <>
            <dt>Checked out</dt>
            <dd>{formatDateTime(loan.checked_out_at)}</dd>
            <dt>Due</dt>
            <dd>
              <strong>{formatDateTime(loan.due_at)}</strong>
            </dd>
          </>
        )}
      </dl>
      {overdue && (
        <p className="loan-late">
          <Icon name="alarm" size={16} /> {loan.days_overdue} days overdue · fee if returned now{" "}
          <strong>{formatPaise(loan.accrued_fee_paise)}</strong>
        </p>
      )}
    </div>
  );
}
