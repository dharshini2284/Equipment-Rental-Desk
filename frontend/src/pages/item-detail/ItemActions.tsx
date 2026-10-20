import { useState, type FormEvent } from "react";
import { api } from "../../api/endpoints";
import type { Item, Loan } from "../../api/types";
import { Alert, ErrorMessage, SuccessMessage } from "../../components/Feedback";
import { Icon } from "../../components/Icon";
import { MemberPicker } from "../../components/MemberPicker";
import { useAction } from "../../hooks/useAction";
import { useAsync } from "../../hooks/useAsync";
import { formatDateTime } from "../../lib/format";
import { formatPaise } from "../../lib/money";

interface Props {
  item: Item;
  onChanged: () => void;
}

type Perform = <T>(call: () => Promise<T>, message: (result: T) => string) => Promise<void>;

/**
 * Only the actions the API lists in `allowed_actions` are rendered, so the desk never sees a
 * button that the current state would reject. The API still checks every rule itself.
 */
export function ItemActions({ item, onChanged }: Props) {
  const action = useAction();
  const allowed = new Set(item.allowed_actions);
  const loan = item.current_loan;

  const perform: Perform = async (call, message) => {
    if (await action.run(call, message)) onChanged();
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>
          <Icon name="hand" /> What happens next
        </h2>
      </div>
      {action.error && <ErrorMessage error={action.error} />}
      {action.success && <SuccessMessage text={action.success} />}

      {allowed.has("reserve") && (
        <ReserveForm item={item} pending={action.pending} perform={perform} />
      )}

      {loan && allowed.has("check_out") && (
        <div className="action">
          <p className="action-lead">
            Hand the item to <strong>{loan.member_name}</strong>. It will be due back in 7 days.
          </p>
          <div className="button-row">
            <button
              type="button"
              className="btn btn-primary"
              disabled={action.pending}
              onClick={() =>
                perform(
                  () => api.checkOut(loan.id),
                  (result: Loan) => `Checked out. Due ${formatDateTime(result.due_at)}.`,
                )
              }
            >
              <Icon name="box" size={16} /> Check out
            </button>
            {allowed.has("cancel_reservation") && (
              <button
                type="button"
                className="btn btn-secondary"
                disabled={action.pending}
                onClick={() =>
                  perform(
                    () => api.cancelReservation(loan.id),
                    () => "Reservation cancelled.",
                  )
                }
              >
                Cancel reservation
              </button>
            )}
          </div>
        </div>
      )}

      {loan && allowed.has("return") && (
        <ReturnForm loan={loan} pending={action.pending} perform={perform} />
      )}

      {allowed.has("send_to_maintenance") && (
        <NoteAction
          label="Send to maintenance"
          icon="wrench"
          hint={
            item.status === "reserved"
              ? "Taking it out of service cancels the current reservation."
              : "The item can't be lent until it is returned to service."
          }
          pending={action.pending}
          onSubmit={(note) =>
            perform(
              () => api.sendToMaintenance(item.id, note),
              () => "Sent to maintenance.",
            )
          }
        />
      )}

      {allowed.has("return_to_service") && (
        <NoteAction
          label="Return to service"
          icon="check"
          primary
          hint="Update the condition note if the repair changed anything."
          pending={action.pending}
          onSubmit={(note) =>
            perform(
              () => api.returnToService(item.id, note),
              () => "Back in service and available.",
            )
          }
        />
      )}
    </div>
  );
}

function ReserveForm({
  item,
  pending,
  perform,
}: {
  item: Item;
  pending: boolean;
  perform: Perform;
}) {
  const [memberId, setMemberId] = useState<number | null>(null);
  const member = useAsync(
    () => (memberId ? api.getMember(memberId) : Promise.resolve(null)),
    String(memberId),
  );
  const blocks = member.data?.eligibility.blocks ?? [];

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!memberId) return;
    perform(
      () => api.reserve(memberId, item.id),
      (loan: Loan) =>
        `Reserved for ${loan.member_name} until ${formatDateTime(loan.reservation_expires_at)}.`,
    ).then(() => setMemberId(null));
  };

  return (
    <form className="action" onSubmit={submit}>
      <p className="action-lead">Reserve this item for a member. The hold lasts 48 hours.</p>
      <MemberPicker selectedId={memberId} onSelect={setMemberId} />
      {member.error && <ErrorMessage error={member.error} />}
      {blocks.length > 0 && (
        <Alert tone="warning" icon="userX" title={`${member.data?.name} cannot borrow right now`}>
          <ul>
            {blocks.map((block) => (
              <li key={block.code}>{block.message}</li>
            ))}
          </ul>
        </Alert>
      )}
      {member.data && blocks.length === 0 && (
        <Alert tone="success" icon="userCheck" title={`${member.data.name} can borrow`} />
      )}
      <button
        type="submit"
        className="btn btn-primary"
        disabled={pending || !memberId || blocks.length > 0 || member.loading}
      >
        <Icon name="hand" size={16} /> Reserve for 48 hours
      </button>
    </form>
  );
}

function ReturnForm({
  loan,
  pending,
  perform,
}: {
  loan: Loan;
  pending: boolean;
  perform: Perform;
}) {
  const [toMaintenance, setToMaintenance] = useState(false);
  const [note, setNote] = useState("");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    perform(
      () =>
        api.returnLoan(loan.id, {
          send_to_maintenance: toMaintenance,
          condition_note: note.trim() || undefined,
        }),
      (result: Loan) =>
        result.fee_charged_paise
          ? `Returned. Late fee of ${formatPaise(result.fee_charged_paise)} added to ${result.member_name}'s balance.`
          : "Returned on time. No fee.",
    );
  };

  const late = loan.status === "overdue";
  return (
    <form className="action" onSubmit={submit}>
      <div className={`fee-preview ${late ? "fee-preview-late" : ""}`}>
        <span>{late ? "Late fee if returned now" : "Returned on time"}</span>
        <strong>{late ? formatPaise(loan.accrued_fee_paise) : "No fee"}</strong>
      </div>
      <label className="field">
        <span>Condition note (optional)</span>
        <input
          maxLength={500}
          placeholder="e.g. blade worn, case cracked"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={toMaintenance}
          onChange={(e) => setToMaintenance(e.target.checked)}
        />
        Needs repair, send it to maintenance
      </label>
      <button type="submit" className="btn btn-primary" disabled={pending}>
        <Icon name="check" size={16} /> Record return
      </button>
    </form>
  );
}

function NoteAction(props: {
  label: string;
  icon: "wrench" | "check";
  primary?: boolean;
  hint: string;
  pending: boolean;
  onSubmit: (note: string | undefined) => void;
}) {
  const [note, setNote] = useState("");
  return (
    <form
      className="action"
      onSubmit={(event) => {
        event.preventDefault();
        props.onSubmit(note.trim() || undefined);
        setNote("");
      }}
    >
      <p className="muted small">{props.hint}</p>
      <div className="inline-form">
        <label className="field">
          <span>Condition note (optional)</span>
          <input maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        <button
          type="submit"
          className={`btn ${props.primary ? "btn-primary" : "btn-secondary"}`}
          disabled={props.pending}
        >
          <Icon name={props.icon} size={16} /> {props.label}
        </button>
      </div>
    </form>
  );
}
