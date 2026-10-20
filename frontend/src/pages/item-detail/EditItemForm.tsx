import { useState, type FormEvent } from "react";
import { api } from "../../api/endpoints";
import type { Item } from "../../api/types";
import { ErrorMessage, SuccessMessage } from "../../components/Feedback";
import { useAction } from "../../hooks/useAction";
import { formatPaise, parseRupeesToPaise } from "../../lib/money";

function paiseToInput(paise: number): string {
  return formatPaise(paise).replace(/[₹,]/g, "");
}

export function EditItemForm({ item, onSaved }: { item: Item; onSaved: () => void }) {
  const [name, setName] = useState(item.name);
  const [category, setCategory] = useState(item.category);
  const [value, setValue] = useState(paiseToInput(item.replacement_value_paise));
  const action = useAction();
  const valuePaise = parseRupeesToPaise(value);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (valuePaise === null) return;
    const ok = await action.run(
      () => api.updateItem(item.id, { name, category, replacement_value_paise: valuePaise }),
      () => "Saved.",
    );
    if (ok) onSaved();
  };

  return (
    <details className="panel collapsible">
      <summary>Edit item details</summary>
      <p className="muted small">
        A new replacement value applies to fees worked out from now on, including the return of a
        loan that is already out.
      </p>
      <form onSubmit={submit}>
        <label className="field">
          <span>Name</span>
          <input required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="field">
          <span>Category</span>
          <input
            required
            maxLength={60}
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          />
        </label>
        <label className="field">
          <span>Replacement value (₹)</span>
          <input
            required
            inputMode="decimal"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            aria-invalid={valuePaise === null}
          />
        </label>
        <button
          type="submit"
          className="btn btn-secondary"
          disabled={action.pending || valuePaise === null}
        >
          Save changes
        </button>
      </form>
      {action.error && <ErrorMessage error={action.error} />}
      {action.success && <SuccessMessage text={action.success} />}
    </details>
  );
}
