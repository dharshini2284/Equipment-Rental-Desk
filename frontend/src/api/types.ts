// Shapes returned by the backend. Money is integer paise; timestamps are UTC ISO strings.

export type ItemStatus = "available" | "reserved" | "checked_out" | "overdue" | "maintenance";
export type LoanStatus =
  | "reserved"
  | "checked_out"
  | "overdue"
  | "returned"
  | "cancelled"
  | "expired";
export type MemberStatus = "active" | "suspended";
export type ItemAction =
  | "reserve"
  | "check_out"
  | "return"
  | "cancel_reservation"
  | "send_to_maintenance"
  | "return_to_service"
  | "join_waitlist";

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Loan {
  id: number;
  member_id: number;
  member_name: string;
  member_phone: string;
  item_id: number;
  item_name: string;
  status: LoanStatus;
  reserved_at: string;
  reservation_expires_at: string;
  checked_out_at: string | null;
  due_at: string | null;
  returned_at: string | null;
  cancelled_at: string | null;
  fee_charged_paise: number | null;
  days_overdue: number;
  accrued_fee_paise: number;
}

export interface Item {
  id: number;
  name: string;
  category: string;
  replacement_value_paise: number;
  condition_note: string;
  status: ItemStatus;
  created_at: string;
  updated_at: string;
  allowed_actions: ItemAction[];
  current_loan: Loan | null;
}

export interface Member {
  id: number;
  name: string;
  phone: string;
  joined_on: string;
  status: MemberStatus;
  created_at: string;
  fee_balance_paise: number;
}

export interface BorrowingBlock {
  code: string;
  message: string;
}

export interface MemberDetail extends Member {
  active_loan_count: number;
  eligibility: { can_borrow: boolean; blocks: BorrowingBlock[] };
  status_history: {
    from_status: MemberStatus;
    to_status: MemberStatus;
    reason: string;
    changed_at: string;
  }[];
}

export interface Payment {
  id: number;
  member_id: number;
  amount_paise: number;
  paid_at: string;
  note: string;
}

export interface Statement {
  member: Member;
  fee_balance_paise: number;
  total_fees_charged_paise: number;
  total_paid_paise: number;
  accrued_unbilled_fees_paise: number;
  loans: Loan[];
  payments: Payment[];
}

export interface ClockInfo {
  now: string;
  test_clock_active: boolean;
  test_clock_allowed: boolean;
}

export interface ApiErrorBody {
  type: string;
  code: string;
  message: string;
  details: Record<string, unknown>;
  request_id: string | null;
}

export type WaitlistStatus = "waiting" | "fulfilled" | "skipped" | "cancelled";

export interface WaitlistEntry {
  id: number;
  item_id: number;
  item_name: string;
  member_id: number;
  member_name: string;
  status: WaitlistStatus;
  /** Place in the live queue; null once resolved. */
  position: number | null;
  joined_at: string;
  resolved_at: string | null;
  loan_id: number | null;
  note: string;
}

export interface Notification {
  id: number;
  member_id: number;
  member_name: string;
  loan_id: number | null;
  kind: string;
  channel: string;
  recipient: string;
  message: string;
  created_at: string;
  delivery: "stub";
}
