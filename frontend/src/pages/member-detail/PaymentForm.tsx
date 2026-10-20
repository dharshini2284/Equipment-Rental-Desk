import { useState, type FormEvent } from "react";
import { api } from "../../api/endpoints";
import type { MemberDetail } from "../../api/types";
import { EmptyState, ErrorMessage, SuccessMessage } from "../../components/Feedback";
import { Icon } from "../../components/Icon";
import { useAction } from "../../hooks/useAction";
import { formatPaise, parseRupeesToPaise } from "../../lib/money";

export function PaymentForm({ member, onPaid }: { member: MemberDetail; onPaid: () => void }) {
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const action = useAction();
  const amountPaise = parseRupeesToPaise(amount);
  const balance = member.fee_balance_paise;
  // Shown early for convenience; the API refuses overpayment regardless.
  const overpaying = amountPaise !== null && amountPaise > balance;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (amountPaise === null) return;
    const ok = await action.run(
      () => api.recordPayment(member.id, amountPaise, note.trim()),
      (result) =>
        `Payment of ${formatPaise(amountPaise)} recorded. Balance now ${formatPaise(result.fee_balance_paise)}.`,
    );
    if (ok) {
      setAmount("");
      setNote("");
      onPaid();
    }
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>
          <Icon name="wallet" /> Record payment
        </h2>
      </div>
      {action.error && <ErrorMessage error={action.error} />}
      {action.success && <SuccessMessage text={action.success} />}
      {balance === 0 ? (
        <EmptyState icon="check">Nothing owed.</EmptyState>
      ) : (
        <form onSubmit={submit}>
          <div className="fee-preview fee-preview-late">
            <span>Outstanding</span>
            <strong>{formatPaise(balance)}</strong>
          </div>
          <label className="field">
            <span>Amount (₹)</span>
            <span className="input-with-action">
              <input
                required
                inputMode="decimal"
                placeholder="0.00"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                aria-invalid={amount !== "" && (amountPaise === null || overpaying)}
              />
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setAmount(formatPaise(balance).replace(/[₹,]/g, ""))}
              >
                Pay in full
              </button>
            </span>
            {amount !== "" && amountPaise === null && (
              <small className="field-error">Enter an amount like 50 or 50.25</small>
            )}
            {overpaying && (
              <small className="field-error">
                That is more than the {formatPaise(balance)} owed. Payments cannot go into credit.
              </small>
            )}
          </label>
          <label className="field">
            <span>Note</span>
            <input
              maxLength={200}
              placeholder="Cash, UPI ref…"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={action.pending || amountPaise === null || overpaying}
          >
            {action.pending ? "Saving…" : "Record payment"}
          </button>
        </form>
      )}
    </div>
  );
}
