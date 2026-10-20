import { useEffect, useRef, useState } from "react";
import { api } from "../api/endpoints";
import { useClock } from "../hooks/useClock";
import { fromIstInputValue, toIstInputValue, toIstIso } from "../lib/clock";
import { formatDateTime } from "../lib/format";
import { Icon } from "./Icon";

const HOUR_MS = 60 * 60 * 1000;
const STEPS: { label: string; ms: number }[] = [
  { label: "+1 h", ms: HOUR_MS },
  { label: "+1 day", ms: 24 * HOUR_MS },
  { label: "+7 days", ms: 7 * 24 * HOUR_MS },
];

/**
 * Reviewer aid: pretend it is a different time. Every API request then carries
 * X-Test-Clock, so expiry, overdue and fee rules can be tried without waiting.
 */
export function ClockControl() {
  const { override, setOverride, version } = useClock();
  const [draft, setDraft] = useState("");
  const [serverAllows, setServerAllows] = useState(true);
  const [open, setOpen] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.clock().then(
      (info) => setServerAllows(info.test_clock_allowed),
      () => undefined, // Pages show their own connection errors.
    );
  }, [version]);

  useEffect(() => {
    setDraft(toIstInputValue(override ? new Date(override) : new Date()));
  }, [override, open]);

  // Close the panel when clicking anywhere else.
  useEffect(() => {
    if (!open) return;
    const onClick = (event: MouseEvent) => {
      if (!wrapper.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const advance = (ms: number) => {
    const base = override ? new Date(override) : new Date();
    setOverride(toIstIso(new Date(base.getTime() + ms)));
  };

  const apply = () => {
    const value = fromIstInputValue(draft);
    if (value) setOverride(value);
  };

  return (
    <div className={`clock ${override ? "clock-active" : ""}`} ref={wrapper}>
      <button
        type="button"
        className="clock-toggle"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <Icon name="clock" size={16} />
        <span>
          {override ? `Review clock: ${formatDateTime(override)}` : "Real time · set review clock"}
        </span>
      </button>
      {open && (
        <div className="clock-panel">
          <p className="clock-title">Review clock</p>
          <p className="muted small">
            Pretend it is another time to try expiry, overdue and fee rules. Sent as the{" "}
            <code>X-Test-Clock</code> header from this browser only.
          </p>
          {!serverAllows && (
            <p className="alert alert-error">The server has the review clock turned off.</p>
          )}
          <label className="field">
            <span>Date and time (IST)</span>
            <input
              type="datetime-local"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
            />
          </label>
          <div className="button-row">
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={apply}
              disabled={!fromIstInputValue(draft)}
            >
              Set
            </button>
            {STEPS.map((step) => (
              <button
                key={step.label}
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => advance(step.ms)}
              >
                {step.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-sm clock-reset"
            onClick={() => setOverride(null)}
            disabled={!override}
          >
            <Icon name="refresh" size={14} /> Back to real time
          </button>
        </div>
      )}
    </div>
  );
}
