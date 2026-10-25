import type { Money } from "../domain";
export function money(value: Money | number | null | undefined): string {
  if (
    value === null ||
    value === undefined ||
    value === "" ||
    !Number.isFinite(Number(value))
  )
    return "Not available";
  return new Intl.NumberFormat("en-BD", {
    style: "currency",
    currency: "BDT",
    currencyDisplay: "narrowSymbol",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value));
}
export function today(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Dhaka",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}
export function date(value: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "Asia/Dhaka",
  }).format(new Date(value.length === 10 ? `${value}T00:00:00+06:00` : value));
}
export function monthRange(month: string) {
  const [year, m] = month.split("-").map(Number);
  return {
    start_date: `${month}-01`,
    end_date:
      month === today().slice(0, 7)
        ? today()
        : `${month}-${new Date(Date.UTC(year, m, 0)).getUTCDate()}`,
  };
}
export function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "Something went wrong. Try again.";
}
