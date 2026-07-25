"use client";

import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type {
  BacktestTrade,
  ExitReason,
  PriceSeriesPoint,
} from "@/lib/strategies/types";

type SpyTradeChartProps = {
  prices: PriceSeriesPoint[];
  trades: BacktestTrade[];
};

type PricePoint = {
  timestamp: number;
  closePrice: number;
};

type TradeMarker = {
  timestamp: number;
  fillPrice: number;
  markerType: "Entry" | "Exit";
  exitReason?: ExitReason;
};

type TooltipEntry = {
  payload?: PricePoint | TradeMarker;
};

type TradeTooltipProps = {
  active?: boolean;
  payload?: readonly TooltipEntry[];
};

const EXIT_LABELS: Record<ExitReason, string> = {
  final_liquidation: "Final liquidation",
  stop_loss: "Stop loss",
  strategy_exit: "Strategy exit",
  take_profit: "Take profit",
};

const currencyFormatter = new Intl.NumberFormat(undefined, {
  currency: "USD",
  style: "currency",
});

function formatDate(timestamp: number): string {
  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(timestamp));
}

function TradeTooltip({ active, payload }: TradeTooltipProps) {
  if (!active || !payload?.length) return null;
  const datum = payload[0]?.payload;
  if (!datum) return null;

  if ("markerType" in datum) {
    return (
      <div className="rounded-md border border-zinc-200 bg-white p-3 text-sm shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
        <p className="font-semibold">{datum.markerType}</p>
        <p>{formatDate(datum.timestamp)}</p>
        <p>{currencyFormatter.format(datum.fillPrice)}</p>
        {datum.exitReason && <p>{EXIT_LABELS[datum.exitReason]}</p>}
      </div>
    );
  }

  return (
    <div className="rounded-md border border-zinc-200 bg-white p-3 text-sm shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
      <p className="font-semibold">SPY close</p>
      <p>{formatDate(datum.timestamp)}</p>
      <p>{currencyFormatter.format(datum.closePrice)}</p>
    </div>
  );
}

export function SpyTradeChart({ prices, trades }: SpyTradeChartProps) {
  const priceData: PricePoint[] = prices.flatMap((point) => {
    const timestamp = Date.parse(point.timestamp);
    const closePrice = Number(point.close_price);
    return Number.isFinite(timestamp) && Number.isFinite(closePrice)
      ? [{ timestamp, closePrice }]
      : [];
  });
  const entries: TradeMarker[] = trades.map((trade) => ({
    fillPrice: Number(trade.entry_price),
    markerType: "Entry",
    timestamp: Date.parse(trade.entry_timestamp),
  }));
  const exits: TradeMarker[] = trades.map((trade) => ({
    exitReason: trade.exit_reason,
    fillPrice: Number(trade.exit_price),
    markerType: "Exit",
    timestamp: Date.parse(trade.exit_timestamp),
  }));

  if (priceData.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-zinc-300 p-6 text-sm text-zinc-500 dark:border-zinc-700">
        SPY price data is unavailable for this preview.
      </p>
    );
  }

  return (
    <>
      <div
        aria-label="SPY closing prices with actual trade entry and exit fills"
        className="h-80 w-full"
        role="img"
      >
        <ResponsiveContainer height="100%" width="100%">
          <ComposedChart data={priceData} margin={{ bottom: 8, left: 8, right: 16, top: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="currentColor" opacity={0.12} />
            <XAxis
              dataKey="timestamp"
              domain={["dataMin", "dataMax"]}
              minTickGap={36}
              scale="time"
              tickFormatter={formatDate}
              type="number"
            />
            <YAxis
              domain={["auto", "auto"]}
              tickFormatter={(value: number) => currencyFormatter.format(value)}
              width={72}
            />
            <Tooltip content={<TradeTooltip />} />
            <Legend />
            <Line
              dataKey="closePrice"
              dot={false}
              isAnimationActive={false}
              name="SPY close"
              stroke="#a1a1aa"
              strokeWidth={1.5}
              type="monotone"
            />
            <Scatter
              data={entries}
              dataKey="fillPrice"
              fill="#10b981"
              isAnimationActive={false}
              name="Entries"
              shape="triangle"
            />
            <Scatter
              data={exits}
              dataKey="fillPrice"
              fill="#f43f5e"
              isAnimationActive={false}
              name="Exits"
              shape="diamond"
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <ul className="sr-only">
        {entries.map((entry, index) => (
          <li key={`entry-${entry.timestamp}-${index}`}>
            Entry on {formatDate(entry.timestamp)} at{" "}
            {currencyFormatter.format(entry.fillPrice)}
          </li>
        ))}
        {exits.map((exit, index) => (
          <li key={`exit-${exit.timestamp}-${index}`}>
            Exit on {formatDate(exit.timestamp)} at{" "}
            {currencyFormatter.format(exit.fillPrice)}:{" "}
            {exit.exitReason ? EXIT_LABELS[exit.exitReason] : "Unknown reason"}
          </li>
        ))}
      </ul>
    </>
  );
}
