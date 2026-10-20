import { download, request } from "./client";
import type {
  ClockInfo,
  Item,
  ItemStatus,
  Loan,
  Member,
  MemberDetail,
  MemberStatus,
  Notification,
  Page,
  Payment,
  Statement,
  WaitlistEntry,
  WaitlistStatus,
} from "./types";

export const PAGE_SIZE = 20;

export const api = {
  clock: () => request<ClockInfo>("GET", "/clock"),

  listItems: (query: { q?: string; status?: ItemStatus | ""; offset?: number; limit?: number }) =>
    request<Page<Item>>("GET", "/items", { query: { limit: PAGE_SIZE, ...query } }),
  getItem: (id: number) => request<Item>("GET", `/items/${id}`),
  createItem: (body: {
    name: string;
    category: string;
    replacement_value_paise: number;
    condition_note: string;
  }) => request<Item>("POST", "/items", { body }),
  updateItem: (
    id: number,
    body: Partial<{
      name: string;
      category: string;
      replacement_value_paise: number;
      condition_note: string;
    }>,
  ) => request<Item>("PATCH", `/items/${id}`, { body }),
  sendToMaintenance: (id: number, conditionNote?: string) =>
    request<Item>("POST", `/items/${id}/send-to-maintenance`, {
      body: conditionNote ? { condition_note: conditionNote } : {},
    }),
  deleteItem: (id: number) => request<void>("DELETE", `/items/${id}`),
  returnToService: (id: number, conditionNote?: string) =>
    request<Item>("POST", `/items/${id}/return-to-service`, {
      body: conditionNote ? { condition_note: conditionNote } : {},
    }),

  listMembers: (query: {
    q?: string;
    status?: MemberStatus | "";
    offset?: number;
    limit?: number;
  }) => request<Page<Member>>("GET", "/members", { query: { limit: PAGE_SIZE, ...query } }),
  getMember: (id: number) => request<MemberDetail>("GET", `/members/${id}`),
  createMember: (body: { name: string; phone: string; joined_on?: string }) =>
    request<Member>("POST", "/members", { body }),
  updateMember: (id: number, body: Partial<{ name: string; phone: string }>) =>
    request<Member>("PATCH", `/members/${id}`, { body }),
  deleteMember: (id: number) => request<void>("DELETE", `/members/${id}`),
  downloadStatementPdf: (id: number) =>
    download(`/members/${id}/statement.pdf`, `statement-member-${id}.pdf`),
  suspendMember: (id: number, reason: string) =>
    request<MemberDetail>("POST", `/members/${id}/suspend`, { body: { reason } }),
  reinstateMember: (id: number, reason: string) =>
    request<MemberDetail>("POST", `/members/${id}/reinstate`, { body: { reason } }),
  getStatement: (id: number) => request<Statement>("GET", `/members/${id}/statement`),
  recordPayment: (id: number, amountPaise: number, note: string) =>
    request<{ payment: Payment; fee_balance_paise: number }>("POST", `/members/${id}/payments`, {
      body: { amount_paise: amountPaise, note },
    }),

  listLoans: (query: { item_id?: number; member_id?: number; offset?: number }) =>
    request<Page<Loan>>("GET", "/loans", { query: { ...query, limit: PAGE_SIZE } }),
  listOverdue: (offset = 0) =>
    request<Page<Loan>>("GET", "/loans/overdue", { query: { offset, limit: 50 } }),
  reserve: (memberId: number, itemId: number) =>
    request<Loan>("POST", "/loans", { body: { member_id: memberId, item_id: itemId } }),
  checkOut: (loanId: number) => request<Loan>("POST", `/loans/${loanId}/checkout`),
  returnLoan: (loanId: number, body: { send_to_maintenance: boolean; condition_note?: string }) =>
    request<Loan>("POST", `/loans/${loanId}/return`, { body }),
  cancelReservation: (loanId: number) => request<Loan>("POST", `/loans/${loanId}/cancel`),

  listWaitlist: (query: { item_id?: number; member_id?: number; status?: WaitlistStatus }) =>
    request<Page<WaitlistEntry>>("GET", "/waitlist", { query: { ...query, limit: 50 } }),
  joinWaitlist: (memberId: number, itemId: number) =>
    request<WaitlistEntry>("POST", "/waitlist", { body: { member_id: memberId, item_id: itemId } }),
  leaveWaitlist: (entryId: number) => request<WaitlistEntry>("POST", `/waitlist/${entryId}/cancel`),

  listNotifications: (query: {
    member_id?: number;
    kind?: string;
    offset?: number;
    limit?: number;
  }) =>
    request<Page<Notification>>("GET", "/notifications", { query: { limit: PAGE_SIZE, ...query } }),
  sendOverdueReminders: () =>
    request<{ queued: number; skipped_recently_reminded: number }>(
      "POST",
      "/notifications/overdue-reminders",
    ),
};
