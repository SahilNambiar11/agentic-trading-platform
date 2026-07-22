"use client";

import { FormEvent, useState } from "react";

type StrategyCreateFormProps = {
  isSubmitting: boolean;
  onSubmit: (name: string, sourceText: string) => Promise<boolean>;
};

export function StrategyCreateForm({ isSubmitting, onSubmit }: StrategyCreateFormProps) {
  // This component owns only the form fields. The parent workspace owns the
  // actual API request so loading/error state stays coordinated with the list.
  const [name, setName] = useState("");
  const [sourceText, setSourceText] = useState("");

  function resetForm() {
    // Reset is local because these values never need to leave this component
    // unless the user submits a valid form.
    setName("");
    setSourceText("");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    // Prevent the browser's full-page form submit and let React run the async
    // create flow supplied by the parent component.
    event.preventDefault();

    if (await onSubmit(name, sourceText)) {
      resetForm();
    }
  }

  return (
    <section className="rounded-md border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <p className="text-sm font-medium text-emerald-700 dark:text-emerald-400">Strategy builder</p>
      <h2 className="mt-1 text-lg font-semibold">New Strategy</h2>
      <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-400">
        Start with a clear trading idea. Parsing and backtesting come next.
      </p>

      <form className="mt-5 space-y-4" onSubmit={(event) => void handleSubmit(event)}>
        <div>
          <label className="text-sm font-medium" htmlFor="strategy-name">
            Strategy name
          </label>
          <input
            className="mt-2 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/20 dark:border-zinc-700 dark:bg-zinc-950"
            disabled={isSubmitting}
            id="strategy-name"
            maxLength={200}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. SPY trend follow"
            required
            value={name}
          />
        </div>

        <div>
          <label className="text-sm font-medium" htmlFor="strategy-source-text">
            Strategy description
          </label>
          <textarea
            className="mt-2 min-h-32 w-full resize-y rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm leading-6 outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/20 dark:border-zinc-700 dark:bg-zinc-950"
            disabled={isSubmitting}
            id="strategy-source-text"
            onChange={(event) => setSourceText(event.target.value)}
            placeholder="Describe the entry, exit, and risk rules in plain language."
            required
            value={sourceText}
          />
        </div>

        <div className="flex flex-wrap gap-3">
          <button
            className="rounded-md bg-zinc-950 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-zinc-50 dark:text-zinc-950 dark:hover:bg-zinc-200"
            disabled={isSubmitting}
            type="submit"
          >
            {isSubmitting ? "Creating..." : "Create strategy"}
          </button>
          <button
            className="rounded-md px-4 py-2.5 text-sm font-medium text-zinc-700 transition hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-60 dark:text-zinc-300 dark:hover:bg-zinc-800"
            disabled={isSubmitting || (!name && !sourceText)}
            onClick={resetForm}
            type="button"
          >
            Reset
          </button>
        </div>
      </form>
    </section>
  );
}
