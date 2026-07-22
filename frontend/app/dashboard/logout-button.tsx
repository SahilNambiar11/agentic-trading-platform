"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { createClient } from "@/lib/supabase/client";

export function LogoutButton() {
  const router = useRouter();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSigningOut, setIsSigningOut] = useState(false);

  async function handleLogout() {
    setErrorMessage(null);
    setIsSigningOut(true);

    try {
      const supabase = createClient();
      const { error } = await supabase.auth.signOut();

      if (error) {
        setErrorMessage(error.message);
        return;
      }

      router.replace("/login");
      router.refresh();
    } catch {
      setErrorMessage("Unable to log out. Please try again.");
    } finally {
      setIsSigningOut(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <button
        className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm font-medium text-zinc-800 transition hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:hover:bg-zinc-800"
        disabled={isSigningOut}
        onClick={handleLogout}
        type="button"
      >
        {isSigningOut ? "Logging out..." : "Log out"}
      </button>
      {errorMessage && (
        <p aria-live="polite" className="text-xs text-red-700 dark:text-red-300">
          {errorMessage}
        </p>
      )}
    </div>
  );
}
