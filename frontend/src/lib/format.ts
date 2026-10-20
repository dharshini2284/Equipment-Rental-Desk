import type { ItemStatus, LoanStatus, MemberStatus } from "../api/types";

const istDateTime = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const istDate = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  day: "numeric",
  month: "short",
  year: "numeric",
});

/** All timestamps are stored in UTC and shown in IST. */
export function formatDateTime(iso: string | null): string {
  return iso ? `${istDateTime.format(new Date(iso))} IST` : "—";
}

/** Calendar dates such as joined_on are already desk-local dates. */
export function formatDate(isoDate: string): string {
  return istDate.format(new Date(`${isoDate}T00:00:00+05:30`));
}

export const ITEM_STATUS_LABELS: Record<ItemStatus, string> = {
  available: "Available",
  reserved: "Reserved",
  checked_out: "Checked out",
  overdue: "Overdue",
  maintenance: "Under maintenance",
};

export const LOAN_STATUS_LABELS: Record<LoanStatus, string> = {
  reserved: "Reserved",
  checked_out: "Checked out",
  overdue: "Overdue",
  returned: "Returned",
  cancelled: "Cancelled",
  expired: "Reservation expired",
};

export const MEMBER_STATUS_LABELS: Record<MemberStatus, string> = {
  active: "Active",
  suspended: "Suspended",
};

/** "in 5 h", "in 2 days", "3 h ago": rough distance between an instant and now. */
export function formatRelative(iso: string, nowMs: number): string {
  const diffMs = new Date(iso).getTime() - nowMs;
  const hours = Math.round(Math.abs(diffMs) / 3_600_000);
  const text =
    hours < 1 ? "under 1 h" : hours < 48 ? `${hours} h` : `${Math.round(hours / 24)} days`;
  return diffMs >= 0 ? `in ${text}` : `${text} ago`;
}

type KindTone = "green" | "blue" | "amber" | "red" | "grey";

/** Labels and colours for the SMS outbox, keyed by the API's notification kind. */
export const NOTIFICATION_KINDS: Record<string, { label: string; tone: KindTone }> = {
  reservation_created: { label: "Reserved", tone: "blue" },
  reservation_cancelled: { label: "Reservation cancelled", tone: "grey" },
  checked_out: { label: "Checked out", tone: "amber" },
  returned: { label: "Returned", tone: "green" },
  waitlist_joined: { label: "Joined waitlist", tone: "blue" },
  waitlist_reserved: { label: "Waitlist: reserved", tone: "blue" },
  waitlist_skipped: { label: "Waitlist: skipped", tone: "red" },
  payment_received: { label: "Payment", tone: "green" },
  member_suspended: { label: "Suspended", tone: "red" },
  member_reinstated: { label: "Reinstated", tone: "green" },
  overdue_reminder: { label: "Overdue reminder", tone: "red" },
};
