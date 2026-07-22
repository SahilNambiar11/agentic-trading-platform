"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import {
  createStrategy,
  deleteStrategy,
  listStrategies,
  StrategyApiError,
  updateStrategy,
} from "@/lib/strategies/api";
import type { Strategy, UpdateStrategyRequest } from "@/lib/strategies/types";

type Notice = { tone: "error" | "success"; message: string } | null;

function formatDate(date: string): string {
  const parsedDate = new Date(date);

  if (Number.isNaN(parsedDate.getTime())) {
    return "Date unavailable";
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsedDate);
}

function getErrorMessage(error: unknown): string {
  if (error instanceof StrategyApiError) {
    return error.message;
  }

  return "Something went wrong. Please try again.";
}

export function StrategyWorkspace() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [isMutating, setIsMutating] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const [createName, setCreateName] = useState("");
  const [createSourceText, setCreateSourceText] = useState("");
  const [expandedStrategyId, setExpandedStrategyId] = useState<string | null>(null);
  const [editingStrategyId, setEditingStrategyId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editSourceText, setEditSourceText] = useState("");
  const [deleteConfirmationId, setDeleteConfirmationId] = useState<string | null>(null);

  const loadStrategies = useCallback(async () => {
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

  function resetCreateForm() {
    setCreateName("");
    setCreateSourceText("");
  }

  function startEditing(strategy: Strategy) {
    setEditingStrategyId(strategy.id);
    setEditName(strategy.name);
    setEditSourceText(strategy.source_text);
    setDeleteConfirmationId(null);
    setNotice(null);
  }

  function cancelEditing() {
    setEditingStrategyId(null);
    setEditName("");
    setEditSourceText("");
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = createName.trim();
    const sourceText = createSourceText.trim();

    if (!name || !sourceText) {
      setNotice({ tone: "error", message: "Enter both a strategy name and description." });
      return;
    }

    if (name.length > 200) {
      setNotice({ tone: "error", message: "Strategy names must be 200 characters or fewer." });
      return;
    }

    setIsCreating(true);
    setNotice(null);

    try {
      await createStrategy({ name, source_text: sourceText, strategy_json: null });
      resetCreateForm();
      await loadStrategies();
      setNotice({ tone: "success", message: "Strategy created." });
    } catch (error) {
      setNotice({ tone: "error", message: getErrorMessage(error) });
    } finally {
      setIsCreating(false);
    }
  }

  async function handleEdit(event: FormEvent<HTMLFormElement>, strategy: Strategy) {
    event.preventDefault();
    const name = editName.trim();
    const sourceText = editSourceText.trim();

    if (!name || !sourceText) {
      setNotice({ tone: "error", message: "Enter both a strategy name and description." });
      return;
    }

    if (name.length > 200) {
      setNotice({ tone: "error", message: "Strategy names must be 200 characters or fewer." });
      return;
    }

    const updates: UpdateStrategyRequest = {};
    if (name !== strategy.name) {
      updates.name = name;
    }
    if (sourceText !== strategy.source_text) {
      updates.source_text = sourceText;
    }

    if (Object.keys(updates).length === 0) {
      cancelEditing();
      setNotice({ tone: "success", message: "No changes to save." });
      return;
    }

    setIsMutating(true);
    setNotice(null);

    try {
      await updateStrategy(strategy.id, updates);
      cancelEditing();
      await loadStrategies();
      setNotice({ tone: "success", message: "Strategy updated." });
    } catch (error) {
      setNotice({ tone: "error", message: getErrorMessage(error) });
    } finally {
      setIsMutating(false);
    }
  }

  async function handleDelete(strategy: Strategy) {
    setIsMutating(true);
    setNotice(null);

    try {
      await deleteStrategy(strategy.id);
      setDeleteConfirmationId(null);
      if (expandedStrategyId === strategy.id) {
        setExpandedStrategyId(null);
      }
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
      <section className="rounded-md border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
        <p className="text-sm font-medium text-emerald-700 dark:text-emerald-400">Strategy builder</p>
        <h2 className="mt-1 text-lg font-semibold">New Strategy</h2>
        <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-400">
          Start with a clear trading idea. Parsing and backtesting come next.
        </p>

        <form className="mt-5 space-y-4" onSubmit={handleCreate}>
          <div>
            <label className="text-sm font-medium" htmlFor="strategy-name">
              Strategy name
            </label>
            <input
              className="mt-2 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/20 dark:border-zinc-700 dark:bg-zinc-950"
              disabled={isCreating}
              id="strategy-name"
              maxLength={200}
              onChange={(event) => setCreateName(event.target.value)}
              placeholder="e.g. SPY trend follow"
              required
              value={createName}
            />
          </div>

          <div>
            <label className="text-sm font-medium" htmlFor="strategy-source-text">
              Strategy description
            </label>
            <textarea
              className="mt-2 min-h-32 w-full resize-y rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm leading-6 outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/20 dark:border-zinc-700 dark:bg-zinc-950"
              disabled={isCreating}
              id="strategy-source-text"
              onChange={(event) => setCreateSourceText(event.target.value)}
              placeholder="Describe the entry, exit, and risk rules in plain language."
              required
              value={createSourceText}
            />
          </div>

          <div className="flex flex-wrap gap-3">
            <button
              className="rounded-md bg-zinc-950 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-zinc-50 dark:text-zinc-950 dark:hover:bg-zinc-200"
              disabled={isCreating}
              type="submit"
            >
              {isCreating ? "Creating..." : "Create strategy"}
            </button>
            <button
              className="rounded-md px-4 py-2.5 text-sm font-medium text-zinc-700 transition hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-60 dark:text-zinc-300 dark:hover:bg-zinc-800"
              disabled={isCreating || (!createName && !createSourceText)}
              onClick={resetCreateForm}
              type="button"
            >
              Reset
            </button>
          </div>
        </form>
      </section>

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
              const isExpanded = expandedStrategyId === strategy.id;
              const isEditing = editingStrategyId === strategy.id;
              const isConfirmingDelete = deleteConfirmationId === strategy.id;

              return (
                <li className="rounded-md border border-zinc-200 p-4 dark:border-zinc-800" key={strategy.id}>
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="min-w-0">
                      <h3 className="break-words font-semibold">{strategy.name}</h3>
                      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                        Updated {formatDate(strategy.updated_at)} · {strategy.strategy_json ? "Parsed" : "Not parsed"}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        aria-expanded={isExpanded}
                        className="rounded-md px-3 py-2 text-sm font-medium text-zinc-700 transition hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-60 dark:text-zinc-300 dark:hover:bg-zinc-800"
                        disabled={isMutating}
                        onClick={() => setExpandedStrategyId(isExpanded ? null : strategy.id)}
                        type="button"
                      >
                        {isExpanded ? "Hide details" : "View details"}
                      </button>
                      <button
                        className="rounded-md border border-zinc-300 px-3 py-2 text-sm font-medium text-zinc-800 transition hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-zinc-700 dark:text-zinc-100 dark:hover:bg-zinc-800"
                        disabled={isMutating}
                        onClick={() => startEditing(strategy)}
                        type="button"
                      >
                        Edit
                      </button>
                      <button
                        className="rounded-md border border-red-300 px-3 py-2 text-sm font-medium text-red-700 transition hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-red-900 dark:text-red-300 dark:hover:bg-red-950/40"
                        disabled={isMutating}
                        onClick={() => setDeleteConfirmationId(strategy.id)}
                        type="button"
                      >
                        Delete
                      </button>
                    </div>
                  </div>

                  {isExpanded && !isEditing && (
                    <div className="mt-4 space-y-4 border-t border-zinc-200 pt-4 dark:border-zinc-800">
                      <div>
                        <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">Description</p>
                        <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-zinc-700 dark:text-zinc-300">
                          {strategy.source_text}
                        </p>
                      </div>
                      <div className="grid gap-3 text-sm sm:grid-cols-2">
                        <p><span className="font-medium">Created:</span> {formatDate(strategy.created_at)}</p>
                        <p><span className="font-medium">Updated:</span> {formatDate(strategy.updated_at)}</p>
                      </div>
                      {strategy.strategy_json && (
                        <div>
                          <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">Parsed strategy</p>
                          <pre className="mt-2 overflow-x-auto rounded-md bg-zinc-100 p-3 text-xs text-zinc-800 dark:bg-zinc-950 dark:text-zinc-200">
                            {JSON.stringify(strategy.strategy_json, null, 2)}
                          </pre>
                        </div>
                      )}
                    </div>
                  )}

                  {isEditing && (
                    <form className="mt-4 space-y-4 border-t border-zinc-200 pt-4 dark:border-zinc-800" onSubmit={(event) => void handleEdit(event, strategy)}>
                      <div>
                        <label className="text-sm font-medium" htmlFor={`edit-name-${strategy.id}`}>Strategy name</label>
                        <input
                          className="mt-2 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/20 dark:border-zinc-700 dark:bg-zinc-950"
                          disabled={isMutating}
                          id={`edit-name-${strategy.id}`}
                          maxLength={200}
                          onChange={(event) => setEditName(event.target.value)}
                          required
                          value={editName}
                        />
                      </div>
                      <div>
                        <label className="text-sm font-medium" htmlFor={`edit-source-${strategy.id}`}>Strategy description</label>
                        <textarea
                          className="mt-2 min-h-32 w-full resize-y rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm leading-6 outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/20 dark:border-zinc-700 dark:bg-zinc-950"
                          disabled={isMutating}
                          id={`edit-source-${strategy.id}`}
                          onChange={(event) => setEditSourceText(event.target.value)}
                          required
                          value={editSourceText}
                        />
                      </div>
                      <div className="flex flex-wrap gap-3">
                        <button className="rounded-md bg-zinc-950 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-zinc-50 dark:text-zinc-950 dark:hover:bg-zinc-200" disabled={isMutating} type="submit">
                          {isMutating ? "Saving..." : "Save changes"}
                        </button>
                        <button className="rounded-md px-4 py-2 text-sm font-medium text-zinc-700 transition hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-60 dark:text-zinc-300 dark:hover:bg-zinc-800" disabled={isMutating} onClick={cancelEditing} type="button">
                          Cancel
                        </button>
                      </div>
                    </form>
                  )}

                  {isConfirmingDelete && (
                    <div className="mt-4 flex flex-wrap items-center gap-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
                      <p className="mr-auto">Delete “{strategy.name}”? This cannot be undone.</p>
                      <button className="rounded-md bg-red-700 px-3 py-2 font-medium text-white transition hover:bg-red-800 disabled:cursor-not-allowed disabled:opacity-60" disabled={isMutating} onClick={() => void handleDelete(strategy)} type="button">
                        {isMutating ? "Deleting..." : "Confirm delete"}
                      </button>
                      <button className="rounded-md px-3 py-2 font-medium transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60 dark:hover:bg-red-950" disabled={isMutating} onClick={() => setDeleteConfirmationId(null)} type="button">
                        Cancel
                      </button>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </>
  );
}
