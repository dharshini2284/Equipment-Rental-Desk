import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/endpoints";
import type { MemberStatus } from "../api/types";
import { Avatar } from "../components/Avatar";
import { EmptyState, ErrorMessage, Loading, SuccessMessage } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { Pagination } from "../components/Pagination";
import { StatusBadge } from "../components/StatusBadge";
import { useAction } from "../hooks/useAction";
import { useAsync } from "../hooks/useAsync";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { formatDate } from "../lib/format";
import { formatPaise } from "../lib/money";

const STATUS_FILTERS: { value: MemberStatus | ""; label: string }[] = [
  { value: "", label: "All" },
  { value: "active", label: "Active" },
  { value: "suspended", label: "Suspended" },
];

export function MembersPage() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<MemberStatus | "">("");
  const [offset, setOffset] = useState(0);
  const [showForm, setShowForm] = useState(false);
  const [createdCount, setCreatedCount] = useState(0);
  const query = useDebouncedValue(search.trim());

  const members = useAsync(
    () => api.listMembers({ q: query, status, offset }),
    `${query}|${status}|${offset}|${createdCount}`,
  );

  return (
    <section>
      <header className="page-header">
        <div>
          <h1>Members</h1>
          <p className="page-sub">
            {members.data ? `${members.data.total} members` : "Registered borrowers"}
          </p>
        </div>
        <div className="page-actions">
          <button type="button" className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
            <Icon name={showForm ? "x" : "plus"} size={16} />{" "}
            {showForm ? "Close" : "Register member"}
          </button>
        </div>
      </header>

      {showForm && <NewMemberForm onCreated={() => setCreatedCount((n) => n + 1)} />}

      <div className="toolbar">
        <label className="search">
          <Icon name="search" size={18} />
          <input
            type="search"
            aria-label="Search"
            placeholder="Search by name or phone"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setOffset(0);
            }}
          />
        </label>
        <div className="chips" role="group" aria-label="Filter by status">
          {STATUS_FILTERS.map((filter) => (
            <button
              key={filter.label}
              type="button"
              className={`filter-chip ${status === filter.value ? "is-active" : ""}`}
              aria-pressed={status === filter.value}
              onClick={() => {
                setStatus(filter.value);
                setOffset(0);
              }}
            >
              {filter.label}
            </button>
          ))}
        </div>
      </div>

      {members.error && <ErrorMessage error={members.error} onRetry={members.reload} />}
      {members.loading && !members.data && <Loading rows={6} />}
      {members.data && members.data.items.length === 0 && (
        <EmptyState icon="users">No members match.</EmptyState>
      )}
      {members.data && members.data.items.length > 0 && (
        <ul className={`panel list member-list ${members.loading ? "is-refreshing" : ""}`}>
          {members.data.items.map((member) => (
            <li key={member.id}>
              <Link to={`/members/${member.id}`} className="list-row list-row-link">
                <Avatar label={member.name} />
                <div className="list-main">
                  <span className="list-title">{member.name}</span>
                  <span className="list-sub">
                    <Icon name="phone" size={13} /> {member.phone} · joined{" "}
                    {formatDate(member.joined_on)}
                  </span>
                </div>
                <div className="list-side">
                  <StatusBadge kind="member" status={member.status} />
                  <span className={`balance ${member.fee_balance_paise > 0 ? "balance-owed" : ""}`}>
                    {member.fee_balance_paise > 0
                      ? `Owes ${formatPaise(member.fee_balance_paise)}`
                      : "No fees owed"}
                  </span>
                </div>
                <Icon name="arrowRight" size={16} />
              </Link>
            </li>
          ))}
        </ul>
      )}
      {members.data && (
        <Pagination
          total={members.data.total}
          limit={members.data.limit}
          offset={members.data.offset}
          onChange={setOffset}
        />
      )}
    </section>
  );
}

function NewMemberForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const action = useAction();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const ok = await action.run(
      () => api.createMember({ name, phone }),
      (member) => `Registered ${member.name}.`,
    );
    if (ok) {
      setName("");
      setPhone("");
      onCreated();
    }
  };

  return (
    <div className="panel panel-form">
      <h2>Register a member</h2>
      <form className="form-grid" onSubmit={submit}>
        <label className="field">
          <span>Full name</span>
          <input required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="field">
          <span>Phone</span>
          <input
            required
            type="tel"
            placeholder="+91 98765 43210"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        </label>
        <div className="form-actions">
          <button type="submit" className="btn btn-primary" disabled={action.pending}>
            {action.pending ? "Saving…" : "Register"}
          </button>
        </div>
      </form>
      {action.error && <ErrorMessage error={action.error} />}
      {action.success && <SuccessMessage text={action.success} />}
    </div>
  );
}
