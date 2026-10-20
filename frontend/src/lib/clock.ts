// The reviewer clock: an optional "now" sent to the API as X-Test-Clock on every request.
// It is kept in localStorage so it survives page reloads, and always expressed in IST.

const STORAGE_KEY = "rental-desk.test-clock";
const IST_OFFSET_MINUTES = 5 * 60 + 30;
const IST_SUFFIX = "+05:30";

let override: string | null = readStored();

function readStored(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function getClockOverride(): string | null {
  return override;
}

export function setClockOverride(value: string | null): void {
  override = value;
  try {
    if (value) window.localStorage.setItem(STORAGE_KEY, value);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage can be blocked (private mode); the override still applies for this tab.
  }
}

/** ISO-8601 string in IST for an instant, e.g. "2026-10-20T10:00:00+05:30". */
export function toIstIso(instant: Date): string {
  const shifted = new Date(instant.getTime() + IST_OFFSET_MINUTES * 60_000);
  return `${shifted.toISOString().slice(0, 19)}${IST_SUFFIX}`;
}

/** Value for an <input type="datetime-local">, showing the instant in IST. */
export function toIstInputValue(instant: Date): string {
  return toIstIso(instant).slice(0, 16);
}

/** Read an <input type="datetime-local"> value as IST. */
export function fromIstInputValue(value: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return null;
  return `${value}:00${IST_SUFFIX}`;
}
