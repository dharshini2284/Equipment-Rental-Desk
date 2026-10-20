import { Link } from "react-router-dom";
import { api } from "../../api/endpoints";
import { ErrorMessage } from "../../components/Feedback";
import { Icon } from "../../components/Icon";
import { useAction } from "../../hooks/useAction";
import { useAsync } from "../../hooks/useAsync";
import { formatDateTime } from "../../lib/format";

/** Items the member is queueing for. Renders nothing if they aren't in any queue. */
export function MemberWaitlist({ memberId, refreshKey }: { memberId: number; refreshKey: string }) {
  const entries = useAsync(
    () => api.listWaitlist({ member_id: memberId, status: "waiting" }),
    `${memberId}|${refreshKey}`,
  );
  const action = useAction();

  if (entries.error) return <ErrorMessage error={entries.error} onRetry={entries.reload} />;
  if (!entries.data || entries.data.items.length === 0) return null;

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>
          <Icon name="queue" /> Waiting for
        </h2>
      </div>
      {action.error && <ErrorMessage error={action.error} />}
      <ul className="list">
        {entries.data.items.map((entry) => (
          <li key={entry.id} className="list-row">
            <span className="queue-position">{entry.position}</span>
            <div className="list-main">
              <Link to={`/items/${entry.item_id}`} className="list-title">
                {entry.item_name}
              </Link>
              <span className="list-sub">
                number {entry.position} in line · joined {formatDateTime(entry.joined_at)}
              </span>
            </div>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={action.pending}
              onClick={() =>
                action
                  .run(
                    () => api.leaveWaitlist(entry.id),
                    () => "Left the waitlist.",
                  )
                  .then((ok) => ok && entries.reload())
              }
            >
              Leave queue
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
