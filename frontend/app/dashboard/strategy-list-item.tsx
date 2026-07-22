"use client";

import { FormEvent } from "react";

import type { Strategy } from "@/lib/strategies/types";

export type StrategyItemMode = "view" | "edit" | "delete" | null;

type StrategyListItemProps = {
  strategy: Strategy;
  mode: StrategyItemMode;
  isMutating: boolean;
  editName: string;
  editSourceText: string;
  onModeChange: (mode: Exclude<StrategyItemMode, null>) => void;
  onCancel: () => void;
  onEditNameChange: (name: string) => void;
  onEditSourceTextChange: (sourceText: string) => void;
  onSave: (event: FormEvent<HTMLFormElement>) => void;
  onDelete: () => void;
};

function formatDate(date: string): string {
  // Backend timestamps are ISO strings. This makes them readable in the user's
  // locale while protecting the UI from malformed dates.
  const parsedDate = new Date(date);

  if (Number.isNaN(parsedDate.getTime())) {
    return "Date unavailable";
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsedDate);
}

export function StrategyListItem({
  strategy,
  mode,
  isMutating,
  editName,
  editSourceText,
  onModeChange,
  onCancel,
  onEditNameChange,
  onEditSourceTextChange,
  onSave,
  onDelete,
}: StrategyListItemProps) {
  // The parent tells each row which mode it is in. Keeping the row mostly
  // controlled avoids each list item inventing separate edit/delete state.
  const isViewing = mode === "view";
  const isEditing = mode === "edit";
  const isConfirmingDelete = mode === "delete";

  return (
    <li className="rounded-md border border-zinc-200 p-4 dark:border-zinc-800">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="break-words font-semibold">{strategy.name}</h3>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Updated {formatDate(strategy.updated_at)} · {strategy.strategy_json ? "Parsed" : "Not parsed"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            aria-expanded={isViewing}
            className="rounded-md px-3 py-2 text-sm font-medium text-zinc-700 transition hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-60 dark:text-zinc-300 dark:hover:bg-zinc-800"
            disabled={isMutating}
            onClick={() => (isViewing ? onCancel() : onModeChange("view"))}
            type="button"
          >
            {isViewing ? "Hide details" : "View details"}
          </button>
          <button
            className="rounded-md border border-zinc-300 px-3 py-2 text-sm font-medium text-zinc-800 transition hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-zinc-700 dark:text-zinc-100 dark:hover:bg-zinc-800"
            disabled={isMutating}
            onClick={() => onModeChange("edit")}
            type="button"
          >
            Edit
          </button>
          <button
            className="rounded-md border border-red-300 px-3 py-2 text-sm font-medium text-red-700 transition hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-red-900 dark:text-red-300 dark:hover:bg-red-950/40"
            disabled={isMutating}
            onClick={() => onModeChange("delete")}
            type="button"
          >
            Delete
          </button>
        </div>
      </div>

      {isViewing && (
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
        <form className="mt-4 space-y-4 border-t border-zinc-200 pt-4 dark:border-zinc-800" onSubmit={onSave}>
          <div>
            <label className="text-sm font-medium" htmlFor={`edit-name-${strategy.id}`}>Strategy name</label>
            <input
              className="mt-2 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/20 dark:border-zinc-700 dark:bg-zinc-950"
              disabled={isMutating}
              id={`edit-name-${strategy.id}`}
              maxLength={200}
              onChange={(event) => onEditNameChange(event.target.value)}
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
              onChange={(event) => onEditSourceTextChange(event.target.value)}
              required
              value={editSourceText}
            />
          </div>
          <div className="flex flex-wrap gap-3">
            <button className="rounded-md bg-zinc-950 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-zinc-50 dark:text-zinc-950 dark:hover:bg-zinc-200" disabled={isMutating} type="submit">
              {isMutating ? "Saving..." : "Save changes"}
            </button>
            <button className="rounded-md px-4 py-2 text-sm font-medium text-zinc-700 transition hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-60 dark:text-zinc-300 dark:hover:bg-zinc-800" disabled={isMutating} onClick={onCancel} type="button">
              Cancel
            </button>
          </div>
        </form>
      )}

      {isConfirmingDelete && (
        <div className="mt-4 flex flex-wrap items-center gap-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
          <p className="mr-auto">Delete “{strategy.name}”? This cannot be undone.</p>
          <button className="rounded-md bg-red-700 px-3 py-2 font-medium text-white transition hover:bg-red-800 disabled:cursor-not-allowed disabled:opacity-60" disabled={isMutating} onClick={onDelete} type="button">
            {isMutating ? "Deleting..." : "Confirm delete"}
          </button>
          <button className="rounded-md px-3 py-2 font-medium transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60 dark:hover:bg-red-950" disabled={isMutating} onClick={onCancel} type="button">
            Cancel
          </button>
        </div>
      )}
    </li>
  );
}
