import { Link } from "react-router-dom";
import type { Loan } from "../api/types";
import { formatDateTime } from "../lib/format";
import { formatPaise } from "../lib/money";
import { Avatar } from "./Avatar";
import { StatusBadge } from "./StatusBadge";

interface Props {
  loans: Loan[];
  /** Hide the column that would repeat the page's own subject. */
  hide?: "member" | "item";
}

function feeText(loan: Loan): string {
  if (loan.fee_charged_paise !== null) return formatPaise(loan.fee_charged_paise);
  if (loan.status === "overdue") return `${formatPaise(loan.accrued_fee_paise)} so far`;
  return "—";
}

function whenText(loan: Loan): string {
  switch (loan.status) {
    case "reserved":
      return `Hold ends ${formatDateTime(loan.reservation_expires_at)}`;
    case "expired":
      return `Hold ended ${formatDateTime(loan.reservation_expires_at)}`;
    case "checked_out":
      return `Due ${formatDateTime(loan.due_at)}`;
    case "overdue":
      return `Due ${formatDateTime(loan.due_at)} (${loan.days_overdue} days late)`;
    case "returned":
      return `Returned ${formatDateTime(loan.returned_at)}`;
    case "cancelled":
      return `Cancelled ${formatDateTime(loan.cancelled_at)}`;
  }
}

export function LoanTable({ loans, hide }: Props) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Loan</th>
            {hide !== "item" && <th>Item</th>}
            {hide !== "member" && <th>Member</th>}
            <th>Status</th>
            <th>Reserved</th>
            <th>Dates</th>
            <th className="num">Fee</th>
          </tr>
        </thead>
        <tbody>
          {loans.map((loan) => (
            <tr key={loan.id}>
              <td data-label="Loan" className="muted">
                #{loan.id}
              </td>
              {hide !== "item" && (
                <td data-label="Item">
                  <Link to={`/items/${loan.item_id}`}>{loan.item_name}</Link>
                </td>
              )}
              {hide !== "member" && (
                <td data-label="Member">
                  <span className="cell-person">
                    <Avatar label={loan.member_name} size="sm" />
                    <Link to={`/members/${loan.member_id}`}>{loan.member_name}</Link>
                  </span>
                </td>
              )}
              <td data-label="Status">
                <StatusBadge kind="loan" status={loan.status} />
              </td>
              <td data-label="Reserved">{formatDateTime(loan.reserved_at)}</td>
              <td data-label="Dates">{whenText(loan)}</td>
              <td data-label="Fee" className="num">
                {feeText(loan)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
