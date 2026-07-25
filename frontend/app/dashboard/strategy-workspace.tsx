"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import {
  deleteStrategy,
  listStrategies,
  StrategyApiError,
  saveConfirmedStrategy,
  updateStrategy,
} from "@/lib/strategies/api";
import type { Strategy, UpdateStrategyRequest } from "@/lib/strategies/types";

import { StrategyCreateForm } from "./strategy-create-form";
import { StrategyJobProgress } from "./strategy-job-progress";
import { StrategyListItem, type StrategyItemMode } from "./strategy-list-item";
import { StrategyReview } from "./strategy-review";
import { validateStrategyInput } from "./strategy-validation";
import { usePreviewJob } from "./use-preview-job";

type Notice = { tone: "error" | "success"; message: string } | null;
type ActiveStrategyAction = { id: string; mode: Exclude<StrategyItemMode, null> } | null;

function getErrorMessage(error: unknown): string {
  // Convert unknown thrown values into UI copy. Expected API failures carry
  // better messages through StrategyApiError.
  return error instanceof StrategyApiError
    ? error.message
    : "Something went wrong. Please try again.";
}

export function StrategyWorkspace() {
  // This is the dashboard's stateful coordinator: it loads strategies, calls the
  // API helper functions, and passes focused props down to presentational pieces.
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSavingPreview, setIsSavingPreview] = useState(false);
  const [pendingName, setPendingName] = useState("");
  const [pendingSourceText, setPendingSourceText] = useState("");
  const [previewConfirmed, setPreviewConfirmed] = useState(false);
  const [isMutating, setIsMutating] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const [activeAction, setActiveAction] = useState<ActiveStrategyAction>(null);
  const [editName, setEditName] = useState("");
  const [editSourceText, setEditSourceText] = useState("");
  const {
    job: previewJob,
    preview,
    error: previewError,
    isSubmitting: isSubmittingPreview,
    isActive: isPreviewing,
    submit: submitPreview,
    reset: resetPreview,
  } = usePreviewJob();

  const loadStrategies = useCallback(async () => {
    // Reload the current user's strategy list from FastAPI.
    setIsLoading(true);
    setLoadError(null);

    try {
      setStrategies(await listStrategies());
    } catch (error) {
      setLoadError(getErrorMessage(error));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    // Initial load on mount. The `isActive` flag prevents state updates if the
    // component unmounts while the network request is still in flight.
    let isActive = true;

    void listStrategies()
      .then((loadedStrategies) => {
        if (isActive) {
          setStrategies(loadedStrategies);
        }
      })
      .catch((error: unknown) => {
        if (isActive) {
          setLoadError(getErrorMessage(error));
        }
      })
      .finally(() => {
        if (isActive) {
          setIsLoading(false);
        }
      });

    return () => {
      isActive = false;
    };
  }, []);

  function clearActiveAction() {
    // Close any open detail/edit/delete panel and clear edit form state.
    setActiveAction(null);
    setEditName("");
    setEditSourceText("");
  }

  function setStrategyMode(strategy: Strategy, mode: Exclude<StrategyItemMode, null>) {
    // Opening edit mode seeds the controlled edit fields with the row's current
    // values. View/delete modes do not need that extra state.
    if (mode === "edit") {
      setEditName(strategy.name);
      setEditSourceText(strategy.source_text);
    }

    setActiveAction({ id: strategy.id, mode });
    setNotice(null);
  }

  async function handlePreview(name: string, sourceText: string): Promise<void> {
    // Validate locally first for quick feedback, then enqueue through FastAPI.
    const result = validateStrategyInput(name, sourceText);
    if (!result.valid) {
      setNotice({ tone: "error", message: result.error });
      return;
    }

    setNotice(null);
    setPendingName(result.value.name);
    setPendingSourceText(result.value.sourceText);
    setPreviewConfirmed(false);
    await submitPreview(result.value.sourceText);
  }

  function invalidatePreview() {
    if (preview || previewJob || previewError) {
      resetPreview();
      setPreviewConfirmed(false);
    }
  }

  async function handleSavePreview() {
    if (!preview) return;
    setIsSavingPreview(true);
    setNotice(null);
    try {
      await saveConfirmedStrategy({
        name: pendingName,
        source_text: pendingSourceText,
        specification: preview.parsed_strategy.specification,
        defaults_applied: preview.parsed_strategy.defaults_applied,
        assumptions: preview.parsed_strategy.assumptions,
        requires_confirmation: preview.parsed_strategy.requires_confirmation,
        confirmed: true,
      });
      resetPreview();
      setPreviewConfirmed(false);
      await loadStrategies();
      setNotice({ tone: "success", message: "Confirmed strategy saved." });
    } catch (error) {
      setNotice({ tone: "error", message: getErrorMessage(error) });
    } finally {
      setIsSavingPreview(false);
    }
  }

  async function handleEdit(event: FormEvent<HTMLFormElement>, strategy: Strategy) {
    // Build a minimal PATCH payload so unchanged fields are not sent.
    event.preventDefault();
    const result = validateStrategyInput(editName, editSourceText);
    if (!result.valid) {
      setNotice({ tone: "error", message: result.error });
      return;
    }

    const updates: UpdateStrategyRequest = {};
    if (result.value.name !== strategy.name) {
      updates.name = result.value.name;
    }
    if (result.value.sourceText !== strategy.source_text) {
      updates.source_text = result.value.sourceText;
    }

    if (Object.keys(updates).length === 0) {
      clearActiveAction();
      setNotice({ tone: "success", message: "No changes to save." });
      return;
    }

    setIsMutating(true);
    setNotice(null);

    try {
      await updateStrategy(strategy.id, updates);
      clearActiveAction();
      await loadStrategies();
      setNotice({ tone: "success", message: "Strategy updated." });
    } catch (error) {
      setNotice({ tone: "error", message: getErrorMessage(error) });
    } finally {
      setIsMutating(false);
    }
  }

  async function handleDelete(strategy: Strategy) {
    // Delete through the API, then reload the list so the UI matches the DB.
    setIsMutating(true);
    setNotice(null);

    try {
      await deleteStrategy(strategy.id);
      clearActiveAction();
      await loadStrategies();
      setNotice({ tone: "success", message: "Strategy deleted." });
    } catch (error) {
      setNotice({ tone: "error", message: getErrorMessage(error) });
    } finally {
      setIsMutating(false);
    }
  }

  return (
    <>
      <StrategyCreateForm
        isPreviewing={isPreviewing}
        onDraftChange={invalidatePreview}
        onPreview={handlePreview}
      />

      <StrategyJobProgress
        error={previewError}
        isSubmitting={isSubmittingPreview}
        job={previewJob}
        onCancel={() => {
          resetPreview();
          setPreviewConfirmed(false);
        }}
        onRetry={() => void handlePreview(pendingName, pendingSourceText)}
      />

      {preview && (
        <StrategyReview
          confirmed={previewConfirmed}
          isSaving={isSavingPreview}
          onCancel={() => {
            resetPreview();
            setPreviewConfirmed(false);
          }}
          onConfirmationChange={setPreviewConfirmed}
          onEditPrompt={() => {
            resetPreview();
            setPreviewConfirmed(false);
          }}
          onSave={() => void handleSavePreview()}
          preview={preview}
        />
      )}

      <section className="rounded-md border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900 lg:col-span-2">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">My Strategies</h2>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              Review and refine the strategies saved to your account.
            </p>
          </div>
          <button
            className="rounded-md border border-zinc-300 px-3 py-2 text-sm font-medium text-zinc-800 transition hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-zinc-700 dark:text-zinc-100 dark:hover:bg-zinc-800"
            disabled={isLoading || isMutating}
            onClick={() => void loadStrategies()}
            type="button"
          >
            {isLoading ? "Refreshing..." : "Refresh"}
          </button>
        </div>

        {notice && (
          <p
            aria-live="polite"
            className={`mt-5 rounded-md border px-3 py-2 text-sm ${
              notice.tone === "error"
                ? "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300"
                : "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200"
            }`}
          >
            {notice.message}
          </p>
        )}

        {isLoading && (
          <div aria-live="polite" className="mt-5 space-y-3">
            <p className="text-sm text-zinc-600 dark:text-zinc-400">Loading your strategies...</p>
            <div className="h-20 animate-pulse rounded-md bg-zinc-100 dark:bg-zinc-800" />
            <div className="h-20 animate-pulse rounded-md bg-zinc-100 dark:bg-zinc-800" />
          </div>
        )}

        {!isLoading && loadError && (
          <div className="mt-5 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
            <p>{loadError}</p>
            <button
              className="mt-3 rounded-md border border-red-300 px-3 py-2 font-medium transition hover:bg-red-100 dark:border-red-800 dark:hover:bg-red-950"
              onClick={() => void loadStrategies()}
              type="button"
            >
              Try again
            </button>
          </div>
        )}

        {!isLoading && !loadError && strategies.length === 0 && (
          <div className="mt-5 rounded-md border border-dashed border-zinc-300 px-4 py-8 text-center dark:border-zinc-700">
            <p className="font-medium">No strategies yet</p>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              Create your first strategy to start building a backtest-ready library.
            </p>
          </div>
        )}

        {!isLoading && !loadError && strategies.length > 0 && (
          <ul className="mt-5 space-y-3" aria-label="Saved strategies">
            {strategies.map((strategy) => {
              const mode = activeAction?.id === strategy.id ? activeAction.mode : null;

              return (
                <StrategyListItem
                  editName={editName}
                  editSourceText={editSourceText}
                  isMutating={isMutating}
                  key={strategy.id}
                  mode={mode}
                  onCancel={clearActiveAction}
                  onDelete={() => void handleDelete(strategy)}
                  onEditNameChange={setEditName}
                  onEditSourceTextChange={setEditSourceText}
                  onModeChange={(nextMode) => setStrategyMode(strategy, nextMode)}
                  onSave={(event) => void handleEdit(event, strategy)}
                  strategy={strategy}
                />
              );
            })}
          </ul>
        )}
      </section>
    </>
  );
}
