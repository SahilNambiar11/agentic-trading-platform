import type { PreviewJob, PreviewJobStage } from "@/lib/strategies/types";

type StrategyJobProgressProps = {
  job: PreviewJob | null;
  isSubmitting: boolean;
  error: string | null;
  onCancel: () => void;
  onRetry: () => void;
};

const STAGE_LABELS: Record<PreviewJobStage, string> = {
  queued: "Queued",
  parsing: "Parsing strategy",
  validating: "Validating strategy",
  compiling: "Compiling strategy",
  loading_data: "Loading historical data",
  backtesting: "Running backtest",
  generating_results: "Generating results",
  completed: "Completed",
  failed: "Failed",
};

export function StrategyJobProgress({
  job,
  isSubmitting,
  error,
  onCancel,
  onRetry,
}: StrategyJobProgressProps) {
  if (!job && !isSubmitting && !error) {
    return null;
  }

  const isActive =
    isSubmitting || job?.status === "queued" || job?.status === "running";
  const isFailed = job?.status === "failed" || (!job && Boolean(error));
  const progress = job?.progress ?? 0;
  const stageLabel = isSubmitting
    ? "Submitting preview job"
    : job
      ? STAGE_LABELS[job.stage]
      : "Unable to start preview";

  return (
    <section
      aria-live="polite"
      className={`rounded-md border p-5 shadow-sm lg:col-span-3 ${
        isFailed
          ? "border-red-300 bg-red-50 dark:border-red-900 dark:bg-red-950/30"
          : "border-emerald-300 bg-white dark:border-emerald-900 dark:bg-zinc-900"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-zinc-500">
            Preview job {job ? `· ${job.status}` : ""}
          </p>
          <h2 className="mt-1 text-lg font-semibold">{stageLabel}</h2>
        </div>
        <span className="text-sm font-semibold tabular-nums">{progress}%</span>
      </div>

      <progress
        aria-label="Strategy preview progress"
        className="mt-4 h-2 w-full accent-emerald-700"
        max={100}
        value={progress}
      />

      {error && (
        <p className="mt-3 text-sm text-red-700 dark:text-red-300">{error}</p>
      )}

      <div className="mt-4 flex flex-wrap gap-3">
        {isActive && (
          <button
            className="rounded-md border border-zinc-300 px-3 py-2 text-sm font-medium transition hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
            onClick={onCancel}
            type="button"
          >
            Cancel
          </button>
        )}
        {isFailed && (
          <button
            className="rounded-md bg-zinc-950 px-3 py-2 text-sm font-medium text-white transition hover:bg-zinc-800 dark:bg-zinc-50 dark:text-zinc-950 dark:hover:bg-zinc-200"
            onClick={onRetry}
            type="button"
          >
            Retry preview
          </button>
        )}
      </div>
    </section>
  );
}
