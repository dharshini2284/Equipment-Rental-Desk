import { useState, type FormEvent } from "react";
import { api } from "../../api/endpoints";
import type { MemberDetail } from "../../api/types";
import { ErrorMessage, SuccessMessage } from "../../components/Feedback";
import { useAction } from "../../hooks/useAction";

export function EditMemberForm({ member, onSaved }: { member: MemberDetail; onSaved: () => void }) {
  const [name, setName] = useState(member.name);
  const [phone, setPhone] = useState(member.phone);
  const action = useAction();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const changes: { name?: string; phone?: string } = {};
    if (name.trim() !== member.name) changes.name = name;
    if (phone !== member.phone) changes.phone = phone;
    if (!changes.name && !changes.phone) return;
    if (
      await action.run(
        () => api.updateMember(member.id, changes),
        () => "Saved.",
      )
    )
      onSaved();
  };

  return (
    <details className="panel collapsible">
      <summary>Edit member details</summary>
      <form className="form-grid" onSubmit={submit}>
        <label className="field">
          <span>Full name</span>
          <input required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="field">
          <span>Phone</span>
          <input required type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
        </label>
        <div className="form-actions">
          <button type="submit" className="btn btn-secondary" disabled={action.pending}>
            Save changes
          </button>
        </div>
      </form>
      {action.error && <ErrorMessage error={action.error} />}
      {action.success && <SuccessMessage text={action.success} />}
    </details>
  );
}
