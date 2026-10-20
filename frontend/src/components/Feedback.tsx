import type { ReactNode } from "react";
import type { ApiError } from "../api/client";
import { Icon, type IconName } from "./Icon";

export function Alert({
  tone,
  icon,
  title,
  children,
}: {
  tone: "error" | "warning" | "success" | "info";
  icon?: IconName;
  title?: ReactNode;
  children?: ReactNode;
}) {
  const fallbackIcon: Record<typeof tone, IconName> = {
    error: "alert",
    warning: "alert",
    success: "check",
    info: "info",
  };
  return (
    <div className={`alert alert-${tone}`} role={tone === "error" ? "alert" : "status"}>
      <span className="alert-icon">
        <Icon name={icon ?? fallbackIcon[tone]} size={18} />
      </span>
      <div className="alert-body">
        {title && <p className="alert-title">{title}</p>}
        {children}
      </div>
    </div>
  );
}

export function ErrorMessage({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  const extra = [...error.blockMessages, ...error.fieldMessages];
  // The headline already joins the block messages; repeat them only when there are several.
  const details = error.blockMessages.length > 1 || error.fieldMessages.length ? extra : [];
  return (
    <Alert tone="error" title={error.message}>
      {details.length > 0 && (
        <ul>
          {details.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
      {(error.requestId || onRetry) && (
        <div className="alert-footer">
          {error.requestId && <small>Reference {error.requestId.slice(0, 12)}</small>}
          {onRetry && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={onRetry}>
              <Icon name="refresh" size={14} /> Try again
            </button>
          )}
        </div>
      )}
    </Alert>
  );
}

export function SuccessMessage({ text }: { text: string }) {
  return <Alert tone="success" title={text} />;
}

/** Grey placeholder blocks shown while the first load is in flight. */
export function Loading({ rows = 4, label = "Loading…" }: { rows?: number; label?: string }) {
  return (
    <div className="skeleton-list" aria-busy="true" aria-label={label}>
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="skeleton-row">
          <span className="skeleton skeleton-avatar" />
          <span className="skeleton-lines">
            <span className="skeleton skeleton-line" />
            <span className="skeleton skeleton-line short" />
          </span>
        </div>
      ))}
    </div>
  );
}

export function EmptyState({ children, icon = "box" }: { children: ReactNode; icon?: IconName }) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Icon name={icon} size={22} />
      </span>
      <p>{children}</p>
    </div>
  );
}
