import { describe, expect, it } from "vitest";
import { formatPaise, parseRupeesToPaise } from "./money";
import { fromIstInputValue, toIstInputValue, toIstIso } from "./clock";

describe("formatPaise", () => {
  it("formats whole rupees with Indian grouping", () => {
    expect(formatPaise(3_200_000)).toBe("₹32,000");
  });
  it("keeps paise", () => {
    expect(formatPaise(12_050)).toBe("₹120.50");
    expect(formatPaise(5)).toBe("₹0.05");
  });
});

describe("parseRupeesToPaise", () => {
  it.each([
    ["150", 15_000],
    ["150.5", 15_050],
    ["0.10", 10],
    ["1,500.75", 150_075],
    ["₹20", 2_000],
  ])("parses %s", (input, expected) => {
    expect(parseRupeesToPaise(input)).toBe(expected);
  });

  it("avoids float rounding (0.29 would be 28.999… paise as a float)", () => {
    expect(parseRupeesToPaise("0.29")).toBe(29);
    expect(parseRupeesToPaise("1.13")).toBe(113);
  });

  it.each(["", "abc", "-5", "1.234", "0", "0.00", "1e3"])("rejects %j", (input) => {
    expect(parseRupeesToPaise(input)).toBeNull();
  });
});

describe("IST clock helpers", () => {
  it("renders an instant in IST", () => {
    expect(toIstIso(new Date("2026-10-20T04:30:00Z"))).toBe("2026-10-20T10:00:00+05:30");
    expect(toIstInputValue(new Date("2026-10-20T20:00:00Z"))).toBe("2026-10-21T01:30");
  });
  it("reads datetime-local input as IST", () => {
    expect(fromIstInputValue("2026-10-20T10:00")).toBe("2026-10-20T10:00:00+05:30");
    expect(fromIstInputValue("nonsense")).toBeNull();
  });
});
