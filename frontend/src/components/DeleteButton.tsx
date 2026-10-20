import { useNavigate } from "react-router-dom";
import { useAction } from "../hooks/useAction";
import { ErrorMessage } from "./Feedback";
import { Icon } from "./Icon";

interface Props {
  /** What is being deleted, for the confirmation prompt, e.g. "item “Jigsaw”". */
  subject: string;
  onDelete: () => Promise<void>;
  /** Where to go once it is gone. */
  redirectTo: string;
}

/** Delete with a browser confirmation. The API refuses if the record has any history. */
export function DeleteButton({ subject, onDelete, redirectTo }: Props) {
  const action = useAction();
  const navigate = useNavigate();

  const remove = async () => {
    if (!window.confirm(`Delete ${subject}? This cannot be undone.`)) return;
    if (await action.run(onDelete, () => "Deleted.")) navigate(redirectTo, { replace: true });
  };

  return (
    <div className="danger-zone">
      {action.error && <ErrorMessage error={action.error} />}
      <p className="muted small">
        Only records with no loans, payments or waitlist entries can be deleted.
      </p>
      <button
        type="button"
        className="btn btn-danger-outline"
        disabled={action.pending}
        onClick={remove}
      >
        <Icon name="trash" size={16} /> Delete {subject.split(" ")[0]}
      </button>
    </div>
  );
}
