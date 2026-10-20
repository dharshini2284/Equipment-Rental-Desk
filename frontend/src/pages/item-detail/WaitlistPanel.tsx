import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/endpoints";
import type { Item } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { EmptyState, ErrorMessage, SuccessMessage } from "../../components/Feedback";
import { Icon } from "../../components/Icon";
import { MemberPicker } from "../../components/MemberPicker";
import { useAction } from "../../hooks/useAction";
import { useAsync } from "../../hooks/useAsync";
import { formatDateTime } from "../../lib/format";

interface Props {
  item: Item;
  /** Bumped by the parent after any action that can change the queue. */
  refreshKey: string;
  onChanged: () => void;
}

/**
 * The item's queue. When the item becomes available the API reserves it for the first
 * member who can borrow at that moment; members who can't are skipped with a reason.
 */
export function WaitlistPanel({ item, refreshKey, onChanged }: Props) {
  const entries = useAsync(
    () => api.listWaitlist({ item_id: item.id }),
    `${item.id}|${refreshKey}`,
  );
  const action = useAction();
  const [memberId, setMemberId] = useState<number | null>(null);
  const canJoin = item.allowed_actions.includes("join_waitlist");

  const waiting = entries.data?.items.filter((entry) => entry.status === "waiting") ?? [];
  const resolved = (entries.data?.items ?? [])
    .filter((entry) => entry.status !== "waiting")
    .slice(-3)
    .reverse();

  const join = async (event: FormEvent) => {
    event.preventDefault();
    if (!memberId) return;
    const ok = await action.run(
      () => api.joinWaitlist(memberId, item.id),
      (entry) => `${entry.member_name} is number ${entry.position} in line.`,
    );
    if (ok) {
      setMemberId(null);
      onChanged();
    }
  };

  const leave = (entryId: number, name: string) =>
    action
      .run(
        () => api.leaveWaitlist(entryId),
        () => `${name} left the waitlist.`,
      )
      .then((ok) => ok && onChanged());

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>
          <Icon name="queue" /> Waitlist
        </h2>
        {waiting.length > 0 && <span className="chip tone-blue">{waiting.length} waiting</span>}
      </div>
      {action.error && <ErrorMessage error={action.error} />}
      {action.success && <SuccessMessage text={action.success} />}
      {entries.error && <ErrorMessage error={entries.error} onRetry={entries.reload} />}

      {waiting.length === 0 ? (
        <EmptyState icon="queue">Nobody is waiting for this item.</EmptyState>
      ) : (
        <ol className="list queue-list">
          {waiting.map((entry) => (
            <li key={entry.id} className="list-row">
              <span className="queue-position">{entry.position}</span>
              <Avatar label={entry.member_name} size="sm" />
              <div className="list-main">
                <Link to={`/members/${entry.member_id}`} className="list-title">
                  {entry.member_name}
                </Link>
                <span className="list-sub">joined {formatDateTime(entry.joined_at)}</span>
              </div>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                disabled={action.pending}
                onClick={() => leave(entry.id, entry.member_name)}
              >
                Remove
              </button>
            </li>
          ))}
        </ol>
      )}

      {resolved.length > 0 && (
        <ul className="queue-history">
          {resolved.map((entry) => (
            <li key={entry.id}>
              <strong>{entry.member_name}</strong>{" "}
              {entry.status === "fulfilled" && "got a reservation"}
              {entry.status === "cancelled" && "left the queue"}
              {entry.status === "skipped" && <>was skipped: {entry.note}</>}
              <span className="muted"> · {formatDateTime(entry.resolved_at)}</span>
            </li>
          ))}
        </ul>
      )}

      {canJoin ? (
        <form className="action" onSubmit={join}>
          <p className="action-lead">
            Add a member to the queue. They are reserved the item automatically when it is their
            turn.
          </p>
          <MemberPicker selectedId={memberId} onSelect={setMemberId} />
          <button
            type="submit"
            className="btn btn-secondary"
            disabled={!memberId || action.pending}
          >
            <Icon name="plus" size={16} /> Join waitlist
          </button>
        </form>
      ) : (
        item.status === "available" && (
          <p className="muted small">The item is available, so reserve it instead of queueing.</p>
        )
      )}
    </div>
  );
}
