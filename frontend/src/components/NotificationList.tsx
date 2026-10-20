import { Link } from "react-router-dom";
import type { Notification } from "../api/types";
import { formatDateTime, NOTIFICATION_KINDS } from "../lib/format";
import { Icon } from "./Icon";

/** Messages as they would appear in the SMS outbox. */
export function NotificationList({
  notifications,
  showMember = true,
}: {
  notifications: Notification[];
  showMember?: boolean;
}) {
  return (
    <ul className="list message-list">
      {notifications.map((notification) => {
        const kind = NOTIFICATION_KINDS[notification.kind] ?? {
          label: notification.kind,
          tone: "grey",
        };
        return (
          <li key={notification.id} className="message">
            <div className="message-head">
              <span className={`chip tone-${kind.tone}`}>{kind.label}</span>
              {showMember && (
                <Link to={`/members/${notification.member_id}`} className="list-title">
                  {notification.member_name}
                </Link>
              )}
              <span className="list-sub">
                <Icon name="phone" size={12} /> {notification.recipient}
              </span>
              <span className="message-time">{formatDateTime(notification.created_at)}</span>
            </div>
            <p className="message-body">{notification.message}</p>
          </li>
        );
      })}
    </ul>
  );
}
