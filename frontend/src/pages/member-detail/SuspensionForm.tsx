import { useState, type FormEvent } from "react";
import { api } from "../../api/endpoints";
import type { MemberDetail } from "../../api/types";
import { ErrorMessage, SuccessMessage } from "../../components/Feedback";
import { Icon } from "../../components/Icon";
import { useAction } from "../../hooks/useAction";

export function SuspensionForm({
  member,
  onChanged,
}: {
  member: MemberDetail;
  onChanged: () => void;
}) {
  const [reason, setReason] = useState("");
  const action = useAction();
  const suspended = member.status === "suspended";

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const ok = await action.run(
      () =>
        suspended
          ? api.reinstateMember(member.id, reason.trim())
          : api.suspendMember(member.id, reason.trim()),
      () => (suspended ? "Member reinstated." : "Member suspended."),
    );
    if (ok) {
      setReason("");
      onChanged();
    }
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>
          <Icon name={suspended ? "userCheck" : "userX"} />{" "}
          {suspended ? "Reinstate member" : "Suspend member"}
        </h2>
      </div>
      {action.error && <ErrorMessage error={action.error} />}
      {action.success && <SuccessMessage text={action.success} />}
      <p className="muted small">
        {suspended
          ? "Reinstating lets the member borrow again. Fee and overdue rules still apply."
          : "A suspended member can't reserve or check out, but can still return items and pay fees."}
      </p>
      <form onSubmit={submit}>
        <label className="field">
          <span>Reason (kept in the member's history)</span>
          <input
            required
            maxLength={300}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
        <button
          type="submit"
          className={`btn ${suspended ? "btn-primary" : "btn-danger"}`}
          disabled={action.pending || !reason.trim()}
        >
          {suspended ? "Reinstate" : "Suspend"}
        </button>
      </form>
    </div>
  );
}
