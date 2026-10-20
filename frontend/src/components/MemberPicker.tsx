import { useState } from "react";
import { api } from "../api/endpoints";
import type { Member } from "../api/types";
import { useAsync } from "../hooks/useAsync";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { formatPaise } from "../lib/money";
import { ErrorMessage } from "./Feedback";
import { Icon } from "./Icon";

interface Props {
  selectedId: number | null;
  onSelect: (memberId: number | null) => void;
}

function optionLabel(member: Member): string {
  const parts = [member.name, member.phone];
  if (member.status === "suspended") parts.push("suspended");
  if (member.fee_balance_paise > 0) parts.push(`owes ${formatPaise(member.fee_balance_paise)}`);
  return parts.join(" · ");
}

/** Search box plus a select of matching members (first 20 by name). */
export function MemberPicker({ selectedId, onSelect }: Props) {
  const [search, setSearch] = useState("");
  const query = useDebouncedValue(search.trim());
  const members = useAsync(() => api.listMembers({ q: query, limit: 20 }), query);

  return (
    <div className="member-picker">
      <label className="field">
        <span>Find member</span>
        <span className="search search-sm">
          <Icon name="search" size={16} />
          <input
            type="search"
            placeholder="Name or phone"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </span>
      </label>
      {members.error && <ErrorMessage error={members.error} onRetry={members.reload} />}
      <label className="field">
        <span>Member</span>
        <select
          value={selectedId ?? ""}
          onChange={(event) => onSelect(event.target.value ? Number(event.target.value) : null)}
        >
          <option value="">
            {members.loading ? "Loading…" : `Choose (${members.data?.total ?? 0} found)`}
          </option>
          {members.data?.items.map((member) => (
            <option key={member.id} value={member.id}>
              {optionLabel(member)}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
