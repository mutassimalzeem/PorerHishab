import { describe, it, expect, vi, afterEach } from "vitest";
import { date, money, monthRange, today } from "../lib/format";
afterEach(() => vi.useRealTimers());
describe("financial display semantics", () => {
  it("keeps unknown distinct from recorded zero", () => {
    expect(money(null)).toBe("Not available");
    expect(money(undefined)).toBe("Not available");
    expect(money("0.00")).not.toBe("Not available");
    expect(money("0.00")).toContain("0.00");
  });
  it("does not invent precision for invalid values", () => {
    expect(money("")).toBe("Not available");
    expect(money("NaN")).toBe("Not available");
  });
  it("preserves expense signs and two decimal places", () => {
    expect(money("-1234.56")).toContain("-");
    expect(money("-1234.56")).toContain("1,234.56");
  });
  it("uses Dhaka dates even when UTC is in the previous day", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-24T19:30:00Z"));
    expect(today()).toBe("2026-10-25");
    expect(date("2026-10-25")).toBe("25 Oct 2026");
  });
  it("ends the running month at today, rather than including future actuals", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-25T06:00:00Z"));
    expect(monthRange("2026-10")).toEqual({
      start_date: "2026-10-01",
      end_date: "2026-10-25",
    });
    expect(monthRange("2024-02").end_date).toBe("2024-02-29");
  });
});
