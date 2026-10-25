import { useId, useState } from "react";
import type { CoachMonth } from "../domain";
import { money } from "../lib/format";
import { Amount, Empty } from "./ui";
export function CashflowChart({ months }: { months: CoachMonth[] }) {
  const id = useId();
  const [selected, setSelected] = useState(0);
  if (!months.length)
    return (
      <Empty title="No outlook points returned">
        Try building the outlook again.
      </Empty>
    );
  const values = months.flatMap((m) => [
    Number(m.balance_without_future_income),
    ...(m.projected_balance === null ? [] : [Number(m.projected_balance)]),
  ]);
  const min = Math.min(0, ...values),
    max = Math.max(1, ...values);
  const extent = max - min || 1;
  const x = (i: number) => 102 + i * (560 / Math.max(1, months.length - 1));
  const y = (value: number) => 220 - ((value - min) / extent) * 166;
  const points = months
    .map((m, i) => `${x(i)},${y(Number(m.balance_without_future_income))}`)
    .join(" ");
  const active = months[Math.min(selected, months.length - 1)];
  const hasForecast = months.some((m) => m.projected_balance !== null);
  const axis = (n: number) =>
    new Intl.NumberFormat("en", {
      notation: "compact",
      maximumFractionDigits: 1,
    }).format(n);
  return (
    <figure className="cashflow-chart">
      <figcaption>
        {hasForecast
          ? "Two possible paths from your starting balance"
          : "Your known-obligation scenario"}
      </figcaption>
      <p className="chart-description">
        {hasForecast
          ? "Compare the historical estimate with a path that counts no future income."
          : "There is not enough history for a forecast. Only scheduled expense reserves are shown."}
      </p>
      <svg
        viewBox="0 0 720 280"
        role="img"
        aria-labelledby={`${id}-title ${id}-desc`}
      >
        <title id={`${id}-title`}>Monthly cashflow scenarios in BDT</title>
        <desc id={`${id}-desc`}>
          Solid ochre indicates the balance without future income. Dashed blue
          indicates an estimate when available. Choose a month below to inspect
          exact amounts, or read the adjacent data table.
        </desc>
        {[min, min + extent / 2, max].map((tick, i) => (
          <g key={i}>
            <line
              x1="94"
              x2="680"
              y1={y(tick)}
              y2={y(tick)}
              className={tick === 0 ? "zero-line" : "grid-line"}
            />
            <text
              x="80"
              y={y(tick) + 4}
              textAnchor="end"
              className="chart-label"
            >
              {axis(tick)}
            </text>
          </g>
        ))}
        <text x="80" y="26" textAnchor="end" className="chart-label">
          BDT
        </text>
        <line
          x1={x(Math.min(selected, months.length - 1))}
          x2={x(Math.min(selected, months.length - 1))}
          y1="40"
          y2="226"
          className="chart-cursor"
        />
        <polyline points={points} className="obligation-line" />
        {months.map((m, i) => {
          const previous = months[i - 1];
          return (
            <g key={m.month}>
              {i > 0 &&
                m.projected_balance !== null &&
                previous.projected_balance !== null && (
                  <line
                    x1={x(i - 1)}
                    y1={y(Number(previous.projected_balance))}
                    x2={x(i)}
                    y2={y(Number(m.projected_balance))}
                    className="forecast-line"
                  />
                )}
              <circle
                cx={x(i)}
                cy={y(Number(m.balance_without_future_income))}
                r={selected === i ? 5 : 3.5}
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
                  r={selected === i ? 5 : 3.5}
                  className="forecast-dot"
                >
                  <title>
                    {m.month}: estimated {money(m.projected_balance)}
                  </title>
                </circle>
              )}
              <text
                x={x(i)}
                y="251"
                textAnchor="middle"
                className="chart-label"
              >
                {months.length > 6 ? m.month.slice(5) : m.month}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="legend">
        <span>
          <i className="solid-key" />
          Without future income
        </span>
        {hasForecast ? (
          <span>
            <i className="dashed-key" />
            Historical estimate
          </span>
        ) : (
          <span>Historical estimate unavailable</span>
        )}
      </div>
      <div
        className="chart-months"
        role="group"
        aria-label="Inspect a cashflow month"
      >
        {months.map((m, i) => (
          <button
            type="button"
            key={m.month}
            aria-pressed={selected === i}
            onClick={() => setSelected(i)}
          >
            {m.month}
          </button>
        ))}
      </div>
      <div className="chart-readout" aria-live="polite">
        <strong>{active.month}</strong>
        <div>
          <small>Without future income</small>
          <Amount value={active.balance_without_future_income} />
        </div>
        <div>
          <small>Estimated balance</small>
          <Amount value={active.projected_balance} />
        </div>
        <div>
          <small>Scheduled expenses</small>
          <Amount value={active.scheduled_expenses} />
        </div>
      </div>
    </figure>
  );
}
