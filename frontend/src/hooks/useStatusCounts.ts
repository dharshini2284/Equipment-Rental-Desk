import { api } from "../api/endpoints";
import type { ItemStatus } from "../api/types";
import { useAsync } from "./useAsync";

export const ITEM_STATUSES: ItemStatus[] = [
  "available",
  "reserved",
  "checked_out",
  "overdue",
  "maintenance",
];

export type StatusCounts = Record<ItemStatus | "all", number>;

/**
 * How many items are in each live status. Uses the list endpoint's `total` with limit=1,
 * so the counts come from the same clock-aware filter the item list uses.
 */
export function useStatusCounts(refreshKey = "") {
  return useAsync(async (): Promise<StatusCounts> => {
    const totals = await Promise.all(
      ITEM_STATUSES.map((status) => api.listItems({ status, limit: 1 }).then((page) => page.total)),
    );
    const counts = { all: 0 } as StatusCounts;
    ITEM_STATUSES.forEach((status, index) => {
      counts[status] = totals[index] ?? 0;
      counts.all += counts[status];
    });
    return counts;
  }, refreshKey);
}
