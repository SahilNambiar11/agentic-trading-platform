"use client";

import type { StrategyPreview } from "@/lib/strategies/types";

type StrategyReviewProps = {
  preview: StrategyPreview;
  confirmed: boolean;
  isSaving: boolean;
  onConfirmationChange: (value: boolean) => void;
  onSave: () => void;
  onEditPrompt: () => void;
  onCancel: () => void;
};

function numberValue(value: string | number | null): number | null {
  if (value === null) return null;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatMoney(value: string | number): string {
  const parsed = numberValue(value);
  return parsed === null
    ? "Unavailable"
    : new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(parsed);
}

function formatPercent(value: string | number | null): string {
  const parsed = numberValue(value);
  return parsed === null ? "Unavailable" : `${parsed.toFixed(2)}%`;
}

function formatDate(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Unavailable" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(parsed);
}

export function StrategyReview({
  preview,
  confirmed,
  isSaving,
  onConfirmationChange,
  onSave,
  onEditPrompt,
  onCancel,
}: StrategyReviewProps) {
  const { parsed_strategy: parsed, backtest } = preview;
  const saveDisabled = isSaving || (parsed.requires_confirmation && !confirmed);

  return (
    <section className="rounded-md border border-emerald-300 bg-white p-6 shadow-sm dark:border-emerald-900 dark:bg-zinc-900 lg:col-span-3">
      <p className="text-sm font-medium text-emerald-700 dark:text-emerald-400">Review before saving</p>
      <h2 className="mt-1 text-xl font-semibold">Strategy backtest preview</h2>

      <div className="mt-6 grid gap-5 lg:grid-cols-2">
        <div className="rounded-md border border-zinc-200 p-4 dark:border-zinc-800">
          <h3 className="font-semibold">Interpreted strategy</h3>
          <p className="mt-3 whitespace-pre-line text-sm leading-6 text-zinc-700 dark:text-zinc-300">{parsed.interpretation}</p>
        </div>
        <div className="rounded-md border border-zinc-200 p-4 dark:border-zinc-800">
          <h3 className="font-semibold">Backtest summary</h3>
          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            <dt className="text-zinc-500">Date range</dt><dd>{formatDate(backtest.start_date)} – {formatDate(backtest.end_date)}</dd>
            <dt className="text-zinc-500">Starting capital</dt><dd>{formatMoney(backtest.starting_cash)}</dd>
            <dt className="text-zinc-500">Ending value</dt><dd>{formatMoney(backtest.ending_value)}</dd>
            <dt className="text-zinc-500">Total return</dt><dd>{formatPercent(backtest.total_return_percent)}</dd>
            <dt className="text-zinc-500">CAGR</dt><dd>{formatPercent(backtest.cagr_percent)}</dd>
            <dt className="text-zinc-500">Maximum drawdown</dt><dd>{formatPercent(backtest.max_drawdown_percent)}</dd>
            <dt className="text-zinc-500">Trades / win rate</dt><dd>{backtest.trade_count} / {formatPercent(backtest.win_rate_percent)}</dd>
            <dt className="text-zinc-500">Buy-and-hold</dt><dd>{formatPercent(backtest.buy_and_hold_return_percent)}</dd>
          </dl>
          <p className="mt-4 text-xs leading-5 text-zinc-500">Historical backtest results are hypothetical and do not guarantee future performance.</p>
        </div>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <div>
          <h3 className="font-semibold">Platform defaults</h3>
          <ul className="mt-2 space-y-2 text-sm text-zinc-700 dark:text-zinc-300">
            {parsed.defaults_applied.length ? parsed.defaults_applied.map((item) => <li key={item.field}>• {item.reason}</li>) : <li>• None.</li>}
          </ul>
        </div>
        <div>
          <h3 className="font-semibold">Assumptions</h3>
          <ul className="mt-2 space-y-2 text-sm text-amber-800 dark:text-amber-300">
            {parsed.assumptions.length ? parsed.assumptions.map((item) => <li key={item.field}>• {item.reason} <span className="text-xs">({item.confidence} confidence)</span></li>) : <li className="text-zinc-700 dark:text-zinc-300">• None.</li>}
          </ul>
        </div>
      </div>

      {parsed.requires_confirmation && (
        <label className="mt-6 flex items-start gap-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-100">
          <input checked={confirmed} className="mt-1" onChange={(event) => onConfirmationChange(event.target.checked)} type="checkbox" />
          <span>I have reviewed and explicitly confirm the assumptions shown above.</span>
        </label>
      )}

      <div className="mt-6 flex flex-wrap gap-3">
        <button className="rounded-md bg-emerald-700 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-60" disabled={saveDisabled} onClick={onSave} type="button">{isSaving ? "Saving..." : "Save Strategy"}</button>
        <button className="rounded-md border border-zinc-300 px-4 py-2.5 text-sm font-medium transition hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800" disabled={isSaving} onClick={onEditPrompt} type="button">Edit prompt</button>
        <button className="rounded-md px-4 py-2.5 text-sm font-medium transition hover:bg-zinc-100 dark:hover:bg-zinc-800" disabled={isSaving} onClick={onCancel} type="button">Cancel</button>
      </div>
      <details className="mt-5 text-sm"><summary className="cursor-pointer text-zinc-500">Developer: normalized strategy JSON</summary><pre className="mt-2 overflow-x-auto rounded-md bg-zinc-100 p-3 text-xs dark:bg-zinc-950">{JSON.stringify(parsed.specification, null, 2)}</pre></details>
    </section>
  );
}
