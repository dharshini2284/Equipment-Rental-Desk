// Money crosses the API as integer paise. These helpers never put a rupee amount through a
// floating-point number: parsing works on the digits of the string.

const PAISE_PER_RUPEE = 100;

export function formatPaise(paise: number): string {
  const sign = paise < 0 ? "-" : "";
  const abs = Math.abs(paise);
  const rupees = Math.floor(abs / PAISE_PER_RUPEE);
  const rest = abs % PAISE_PER_RUPEE;
  const rupeeText = rupees.toLocaleString("en-IN");
  return rest === 0
    ? `${sign}₹${rupeeText}`
    : `${sign}₹${rupeeText}.${String(rest).padStart(2, "0")}`;
}

/**
 * Parse "150", "150.5" or "1,500.75" into paise. Returns null for anything that is not a
 * positive amount with at most two decimal places.
 */
export function parseRupeesToPaise(input: string): number | null {
  const cleaned = input.trim().replace(/,/g, "").replace(/^₹/, "");
  const match = /^(\d{1,9})(?:\.(\d{1,2}))?$/.exec(cleaned);
  if (!match) return null;
  const rupees = Number(match[1]);
  const paise = Number((match[2] ?? "").padEnd(2, "0"));
  const total = rupees * PAISE_PER_RUPEE + paise;
  return total > 0 ? total : null;
}
