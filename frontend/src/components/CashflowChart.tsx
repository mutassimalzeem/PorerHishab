import { useId } from "react";
import type { CoachMonth } from "../domain";
import { money } from "../lib/format";
export function CashflowChart({ months }: { months: CoachMonth[] }) {
  const id = useId();
  const values = months.flatMap((m) => [
    Number(m.balance_without_future_income),
    ...(m.projected_balance !== null ? [Number(m.projected_balance)] : []),
  ]);
  const min = Math.min(0, ...values),
    max = Math.max(1, ...values),
    span = max - min;
  const x = (i: number) => 60 + i * (600 / Math.max(1, months.length - 1));
  const y = (n: number) => 190 - ((n - min) / span) * 150;
  const observed = months
    .map((m, i) => `${x(i)},${y(Number(m.balance_without_future_income))}`)
    .join(" ");
  const estimated = months
    .flatMap((m, i) =>
      m.projected_balance === null
        ? []
        : [`${x(i)},${y(Number(m.projected_balance))}`],
    )
    .join(" ");
  return (
    <figure className="cashflow-chart">
      <figcaption>Two possible paths from your starting balance</figcaption>
      <svg viewBox="0 0 720 250" role="img" aria-labelledby={id}>
        <title id={id}>
          Projected balance versus balance without future income. Exact values
          are in the table below.
        </title>
        <line x1="50" x2="680" y1={y(0)} y2={y(0)} className="zero-line" />
        <text x="8" y={y(0) - 8} className="chart-label">
          BDT 0
        </text>
        <polyline points={observed} className="obligation-line" />
        {estimated && <polyline points={estimated} className="forecast-line" />}
        {months.map((m, i) => (
          <g key={m.month}>
            <circle
              cx={x(i)}
              cy={y(Number(m.balance_without_future_income))}
              r="4"
              className="obligation-dot"
            >
              <title>
                {m.month}: without future income{" "}
                {money(m.balance_without_future_income)}
              </title>
            </circle>
            {m.projected_balance !== null && (
              <circle
                cx={x(i)}
                cy={y(Number(m.projected_balance))}
                r="4"
                className="forecast-dot"
              >
                <title>
                  {m.month}: estimated {money(m.projected_balance)}
                </title>
              </circle>
            )}
            <text x={x(i)} y="232" textAnchor="middle" className="chart-label">
              {m.month}
            </text>
          </g>
        ))}
      </svg>
      <div className="legend">
        <span>
          <i className="solid-key" />
          Without future income
        </span>
        <span>
          <i className="dashed-key" />
          Historical estimate
        </span>
      </div>
    </figure>
  );
}
