import { useSearchParams } from "react-router-dom";
import { api } from "../api/endpoints";
import { Alert, EmptyState, ErrorMessage, Loading, SuccessMessage } from "../components/Feedback";
import { Icon } from "../components/Icon";
import { NotificationList } from "../components/NotificationList";
import { Pagination } from "../components/Pagination";
import { useAction } from "../hooks/useAction";
import { useAsync } from "../hooks/useAsync";
import { NOTIFICATION_KINDS } from "../lib/format";

const KIND_FILTERS = [
  "overdue_reminder",
  "reservation_created",
  "waitlist_reserved",
  "waitlist_skipped",
  "returned",
  "payment_received",
];

export function OutboxPage() {
  const [params, setParams] = useSearchParams();
  const kind = params.get("kind") ?? "";
  const memberId = Number(params.get("member_id")) || undefined;
  const offset = Number(params.get("offset") ?? 0) || 0;
  const reminders = useAction();

  const messages = useAsync(
    () => api.listNotifications({ kind, member_id: memberId, offset }),
    `${kind}|${memberId}|${offset}|${reminders.success ?? ""}`,
  );

  const update = (changes: Record<string, string | number | undefined>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value === undefined || value === "" || value === 0) next.delete(key);
      else next.set(key, String(value));
    }
    setParams(next, { replace: true });
  };

  return (
    <section>
      <header className="page-header">
        <div>
          <h1>Outbox</h1>
          <p className="page-sub">SMS messages the desk sends to members, newest first.</p>
        </div>
        <div className="page-actions">
          <button
            type="button"
            className="btn btn-primary"
            disabled={reminders.pending}
            onClick={() =>
              reminders.run(api.sendOverdueReminders, (result) =>
                result.queued
                  ? `Queued ${result.queued} overdue reminder${result.queued === 1 ? "" : "s"}.`
                  : `No reminders queued: every overdue loan was reminded in the last 24 hours (${result.skipped_recently_reminded}).`,
              )
            }
          >
            <Icon name="send" size={16} /> Send overdue reminders
          </button>
        </div>
      </header>

      <Alert tone="info" title="Delivery is a stub.">
        Messages are recorded here when the action that triggers them is saved, but no SMS is
        actually sent.
      </Alert>
      {reminders.error && <ErrorMessage error={reminders.error} />}
      {reminders.success && <SuccessMessage text={reminders.success} />}

      <div className="toolbar">
        <div className="chips" role="group" aria-label="Filter by message type">
          <button
            type="button"
            className={`filter-chip ${kind === "" ? "is-active" : ""}`}
            onClick={() => update({ kind: "", offset: 0 })}
          >
            All
          </button>
          {KIND_FILTERS.map((option) => (
            <button
              key={option}
              type="button"
              className={`filter-chip ${kind === option ? "is-active" : ""}`}
              aria-pressed={kind === option}
              onClick={() => update({ kind: option, offset: 0 })}
            >
              {NOTIFICATION_KINDS[option]?.label ?? option}
            </button>
          ))}
        </div>
        {memberId && (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => update({ member_id: undefined, offset: 0 })}
          >
            <Icon name="x" size={14} /> Only member #{memberId}
          </button>
        )}
      </div>

      {messages.error && <ErrorMessage error={messages.error} onRetry={messages.reload} />}
      {messages.loading && !messages.data && <Loading rows={5} />}
      {messages.data && messages.data.items.length === 0 && (
        <EmptyState icon="message">No messages match.</EmptyState>
      )}
      {messages.data && messages.data.items.length > 0 && (
        <div className={`panel ${messages.loading ? "is-refreshing" : ""}`}>
          <NotificationList notifications={messages.data.items} />
        </div>
      )}
      {messages.data && (
        <Pagination
          total={messages.data.total}
          limit={messages.data.limit}
          offset={messages.data.offset}
          onChange={(next) => update({ offset: next })}
        />
      )}
    </section>
  );
}
