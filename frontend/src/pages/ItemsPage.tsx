import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import type { Item, ItemStatus } from "../api/types";
import { Avatar } from "../components/Avatar";
import { EmptyState, ErrorMessage, Loading, SuccessMessage } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { Pagination } from "../components/Pagination";
import { StatusBadge } from "../components/StatusBadge";
import { useAction } from "../hooks/useAction";
import { useAsync } from "../hooks/useAsync";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { ITEM_STATUSES, useStatusCounts } from "../hooks/useStatusCounts";
import { formatDateTime, ITEM_STATUS_LABELS } from "../lib/format";
import { formatPaise, parseRupeesToPaise } from "../lib/money";

export function ItemsPage() {
  const [params, setParams] = useSearchParams();
  const status = (params.get("status") ?? "") as ItemStatus | "";
  const offset = Number(params.get("offset") ?? 0) || 0;
  const [search, setSearch] = useState(params.get("q") ?? "");
  const [showForm, setShowForm] = useState(false);
  const [createdCount, setCreatedCount] = useState(0);
  const query = useDebouncedValue(search.trim());

  const updateParams = (changes: Record<string, string | number>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value === "" || value === 0) next.delete(key);
      else next.set(key, String(value));
    }
    setParams(next, { replace: true });
  };

  useEffect(() => {
    if (query !== (params.get("q") ?? "")) updateParams({ q: query, offset: 0 });
    // Only react to the debounced search text.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  const items = useAsync(
    () => api.listItems({ q: query, status, offset }),
    `${query}|${status}|${offset}|${createdCount}`,
  );
  const counts = useStatusCounts(String(createdCount));

  return (
    <section>
      <header className="page-header">
        <div>
          <h1>Items</h1>
          <p className="page-sub">
            {counts.data ? `${counts.data.all} items in the library` : "The library's equipment"}
          </p>
        </div>
        <div className="page-actions">
          <button type="button" className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
            <Icon name={showForm ? "x" : "plus"} size={16} /> {showForm ? "Close" : "Add item"}
          </button>
        </div>
      </header>

      {showForm && <NewItemForm onCreated={() => setCreatedCount((n) => n + 1)} />}

      <div className="toolbar">
        <label className="search">
          <Icon name="search" size={18} />
          <input
            type="search"
            aria-label="Search"
            placeholder="Search by name or category"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <div className="chips" role="group" aria-label="Filter by status">
          <button
            type="button"
            className={`filter-chip ${status === "" ? "is-active" : ""}`}
            onClick={() => updateParams({ status: "", offset: 0 })}
          >
            All <span className="filter-count">{counts.data?.all ?? "·"}</span>
          </button>
          {ITEM_STATUSES.map((option) => (
            <button
              key={option}
              type="button"
              className={`filter-chip filter-${option} ${status === option ? "is-active" : ""}`}
              aria-pressed={status === option}
              onClick={() => updateParams({ status: option, offset: 0 })}
            >
              {ITEM_STATUS_LABELS[option]}{" "}
              <span className="filter-count">{counts.data?.[option] ?? "·"}</span>
            </button>
          ))}
        </div>
      </div>

      {items.error && <ErrorMessage error={items.error} onRetry={items.reload} />}
      {items.loading && !items.data && <Loading rows={6} />}
      {items.data && items.data.items.length === 0 && (
        <EmptyState icon="search">No items match these filters.</EmptyState>
      )}
      {items.data && items.data.items.length > 0 && (
        <div className={`card-grid ${items.loading ? "is-refreshing" : ""}`}>
          {items.data.items.map((item) => (
            <ItemCard key={item.id} item={item} />
          ))}
        </div>
      )}
      {items.data && (
        <Pagination
          total={items.data.total}
          limit={items.data.limit}
          offset={items.data.offset}
          onChange={(next) => updateParams({ offset: next })}
        />
      )}
    </section>
  );
}

function ItemCard({ item }: { item: Item }) {
  const loan = item.current_loan;
  return (
    <Link to={`/items/${item.id}`} className={`item-card status-${item.status}`}>
      <div className="item-card-top">
        <Avatar label={item.name} colorKey={item.category} />
        <StatusBadge kind="item" status={item.status} />
      </div>
      <h3 className="item-card-name">{item.name}</h3>
      <p className="item-card-category">{item.category}</p>
      <div className="item-card-foot">
        <span className="item-card-value">{formatPaise(item.replacement_value_paise)}</span>
        {loan && (
          <span className="item-card-holder">
            <Icon name="users" size={13} /> {loan.member_name}
          </span>
        )}
      </div>
      {loan?.status === "overdue" && (
        <p className="item-card-note tone-red">{loan.days_overdue} days overdue</p>
      )}
      {loan?.status === "checked_out" && (
        <p className="item-card-note">Due {formatDateTime(loan.due_at)}</p>
      )}
      {loan?.status === "reserved" && (
        <p className="item-card-note">Hold ends {formatDateTime(loan.reservation_expires_at)}</p>
      )}
    </Link>
  );
}

function NewItemForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  const action = useAction();
  const valuePaise = parseRupeesToPaise(value);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (valuePaise === null) return;
    const ok = await action.run(
      () =>
        api.createItem({
          name,
          category,
          replacement_value_paise: valuePaise,
          condition_note: note,
        }),
      (item) => `Added “${item.name}”.`,
    );
    if (ok) {
      setName("");
      setCategory("");
      setValue("");
      setNote("");
      onCreated();
    }
  };

  return (
    <div className="panel panel-form">
      <h2>Add an item</h2>
      <form className="form-grid" onSubmit={submit}>
        <label className="field">
          <span>Name</span>
          <input required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="field">
          <span>Category</span>
          <input
            required
            maxLength={60}
            placeholder="Power tools"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          />
        </label>
        <label className="field">
          <span>Replacement value (₹)</span>
          <input
            required
            inputMode="decimal"
            placeholder="4500"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            aria-invalid={value !== "" && valuePaise === null}
          />
          {value !== "" && valuePaise === null && (
            <small className="field-error">Enter an amount like 4500 or 4500.50</small>
          )}
        </label>
        <label className="field">
          <span>Condition note</span>
          <input maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        <div className="form-actions">
          <button
            type="submit"
            className="btn btn-primary"
            disabled={action.pending || valuePaise === null}
          >
            {action.pending ? "Saving…" : "Add item"}
          </button>
        </div>
      </form>
      {action.error && <ErrorMessage error={action.error} />}
      {action.success && <SuccessMessage text={action.success} />}
    </div>
  );
}
