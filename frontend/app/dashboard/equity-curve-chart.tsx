"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { EquityCurvePoint } from "@/lib/strategies/types";

type EquityCurveChartProps = {
  points: EquityCurvePoint[];
};

type ChartPoint = {
  timestamp: number;
  strategyValue: number;
  buyAndHoldValue: number;
};

const moneyFormatter = new Intl.NumberFormat(undefined, {
  currency: "USD",
  maximumFractionDigits: 0,
  notation: "compact",
  style: "currency",
});

function formatDate(timestamp: number): string {
  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(timestamp));
}

export function EquityCurveChart({ points }: EquityCurveChartProps) {
  const chartData: ChartPoint[] = points.flatMap((point) => {
    const timestamp = Date.parse(point.timestamp);
    const strategyValue = Number(point.strategy_value);
    const buyAndHoldValue = Number(point.buy_and_hold_value);
    return Number.isFinite(timestamp) &&
      Number.isFinite(strategyValue) &&
      Number.isFinite(buyAndHoldValue)
      ? [{ timestamp, strategyValue, buyAndHoldValue }]
      : [];
  });

  if (chartData.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-zinc-300 p-6 text-sm text-zinc-500 dark:border-zinc-700">
        Equity-curve data is unavailable for this preview.
      </p>
    );
  }

  return (
    <div
      aria-label="Strategy and SPY buy-and-hold portfolio values over time"
      className="h-80 w-full"
      role="img"
    >
      <ResponsiveContainer height="100%" width="100%">
        <LineChart data={chartData} margin={{ bottom: 8, left: 8, right: 16, top: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="currentColor" opacity={0.12} />
          <XAxis
            dataKey="timestamp"
            domain={["dataMin", "dataMax"]}
            minTickGap={36}
            scale="time"
            tickFormatter={formatDate}
            type="number"
          />
          <YAxis tickFormatter={(value: number) => moneyFormatter.format(value)} width={72} />
          <Tooltip
            formatter={(value, name) => [
              new Intl.NumberFormat(undefined, {
                currency: "USD",
                style: "currency",
              }).format(Number(value)),
              name === "strategyValue" ? "Strategy" : "SPY buy-and-hold",
            ]}
            labelFormatter={(value) => formatDate(Number(value))}
          />
          <Legend
            formatter={(value) =>
              value === "strategyValue" ? "Strategy" : "SPY buy-and-hold"
            }
          />
          <Line
            dataKey="strategyValue"
            dot={false}
            isAnimationActive={false}
            stroke="#10b981"
            strokeWidth={2}
            type="monotone"
          />
          <Line
            dataKey="buyAndHoldValue"
            dot={false}
            isAnimationActive={false}
            stroke="#60a5fa"
            strokeWidth={2}
            type="monotone"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
