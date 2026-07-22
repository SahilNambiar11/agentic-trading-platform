"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { createClient } from "@/lib/supabase/client";

export default function SignupPage() {
  const router = useRouter();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage(null);

    const formData = new FormData(event.currentTarget);
    const email = String(formData.get("email") ?? "").trim();
    const password = String(formData.get("password") ?? "");
    const confirmPassword = String(formData.get("confirmPassword") ?? "");

    if (!/^\S+@\S+\.\S+$/.test(email)) {
      setErrorMessage("Enter a valid email address.");
      return;
    }

    if (password.length < 8) {
      setErrorMessage("Password must be at least 8 characters.");
      return;
    }

    if (password !== confirmPassword) {
      setErrorMessage("Passwords do not match.");
      return;
    }

    setIsSubmitting(true);

    try {
      const supabase = createClient();
      const { error } = await supabase.auth.signUp({ email, password });

      if (error) {
        setErrorMessage(error.message);
        return;
      }

      router.replace("/dashboard");
      router.refresh();
    } catch {
      setErrorMessage("Unable to create your account. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-50 px-6 py-16 text-zinc-950 dark:bg-zinc-950 dark:text-zinc-50">
      <section className="w-full max-w-md">
        <div className="mb-8">
          <p className="text-sm font-medium text-emerald-700 dark:text-emerald-400">
            Agentic Trading
          </p>
          <h1 className="mt-2 text-3xl font-semibold">Create your account</h1>
          <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
            Start building and evaluating trading strategies.
          </p>
        </div>

        <form
          className="space-y-5 rounded-md border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900"
          onSubmit={handleSubmit}
        >
          <div>
            <label className="text-sm font-medium" htmlFor="email">
              Email
            </label>
            <input
              autoComplete="email"
              className="mt-2 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/20 dark:border-zinc-700 dark:bg-zinc-950"
              id="email"
              name="email"
              required
              type="email"
            />
          </div>

          <div>
            <label className="text-sm font-medium" htmlFor="password">
              Password
            </label>
            <input
              autoComplete="new-password"
              className="mt-2 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/20 dark:border-zinc-700 dark:bg-zinc-950"
              id="password"
              minLength={8}
              name="password"
              required
              type="password"
            />
            <p className="mt-1 text-xs text-zinc-500">At least 8 characters.</p>
          </div>

          <div>
            <label className="text-sm font-medium" htmlFor="confirmPassword">
              Confirm password
            </label>
            <input
              autoComplete="new-password"
              className="mt-2 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/20 dark:border-zinc-700 dark:bg-zinc-950"
              id="confirmPassword"
              minLength={8}
              name="confirmPassword"
              required
              type="password"
            />
          </div>

          {errorMessage && (
            <p
              aria-live="polite"
              className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300"
            >
              {errorMessage}
            </p>
          )}

          <button
            className="w-full rounded-md bg-zinc-950 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-zinc-50 dark:text-zinc-950 dark:hover:bg-zinc-200"
            disabled={isSubmitting}
            type="submit"
          >
            {isSubmitting ? "Creating account..." : "Create account"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-zinc-600 dark:text-zinc-400">
          Already have an account?{" "}
          <Link
            className="font-medium text-emerald-700 hover:underline dark:text-emerald-400"
            href="/login"
          >
            Log in
          </Link>
        </p>
      </section>
    </main>
  );
}
