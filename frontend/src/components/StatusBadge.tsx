import type { ItemStatus, LoanStatus, MemberStatus } from "../api/types";
import { ITEM_STATUS_LABELS, LOAN_STATUS_LABELS, MEMBER_STATUS_LABELS } from "../lib/format";
import type { Tone } from "./StatCard";

export const STATUS_TONES: Record<string, Tone> = {
  available: "green",
  active: "green",
  returned: "grey",
  reserved: "blue",
  checked_out: "amber",
  overdue: "red",
  suspended: "red",
  maintenance: "grey",
  cancelled: "grey",
  expired: "grey",
};

type Props =
  | { kind: "item"; status: ItemStatus }
  | { kind: "loan"; status: LoanStatus }
  | { kind: "member"; status: MemberStatus };

export function StatusBadge(props: Props) {
  const label =
    props.kind === "item"
      ? ITEM_STATUS_LABELS[props.status]
      : props.kind === "loan"
        ? LOAN_STATUS_LABELS[props.status]
        : MEMBER_STATUS_LABELS[props.status];
  return (
    <span className={`badge tone-${STATUS_TONES[props.status] ?? "grey"}`}>
      <span className="badge-dot" />
      {label}
    </span>
  );
}
