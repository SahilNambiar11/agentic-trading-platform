import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";

import { LogoutButton } from "./logout-button";
import { StrategyWorkspace } from "./strategy-workspace";

export default async function DashboardPage() {
  const supabase = await createClient();
  const {
    data: { user },
    error,
  } = await supabase.auth.getUser();

  if (error || !user) {
    redirect("/login");
  }

  return (
    <main className="min-h-screen bg-zinc-50 text-zinc-950 dark:bg-zinc-950 dark:text-zinc-50">
      <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        <div className="mx-auto flex w-full max-w-6xl items-start justify-between gap-6 px-6 py-5">
          <div>
            <p className="text-sm font-medium text-emerald-700 dark:text-emerald-400">
              Agentic Trading
            </p>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              Signed in as {user.email ?? "Email unavailable"}
            </p>
          </div>
          <LogoutButton />
        </div>
      </header>

      <div className="mx-auto w-full max-w-6xl px-6 py-10">
        <div className="mb-8">
          <h1 className="text-3xl font-semibold">Dashboard</h1>
          <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
            Build strategies, run backtests, and review results.
          </p>
        </div>

        <div className="grid gap-5 lg:grid-cols-3">
          <StrategyWorkspace />
          <section className="min-h-48 rounded-md border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900 lg:col-span-3">
            <h2 className="text-lg font-semibold">Recent Backtests</h2>
            <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-400">
              Completed and in-progress backtests will appear here.
            </p>
          </section>
        </div>
      </div>
    </main>
  );
}
