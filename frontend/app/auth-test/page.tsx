"use client";

import { useEffect, useState } from "react";

import { createClient } from "@/lib/supabase/client";

type ConnectionState =
  | { status: "checking" }
  | { status: "success"; authenticated: boolean }
  | { status: "error" };

export default function AuthTestPage() {
  // Small diagnostics page for checking whether the browser can create a
  // Supabase client and read the current session.
  const [connection, setConnection] = useState<ConnectionState>({
    status: "checking",
  });

  useEffect(() => {
    let active = true;

    async function checkSession() {
      // This does not call FastAPI; it only verifies the frontend/Supabase link.
      try {
        const supabase = createClient();
        const { data, error } = await supabase.auth.getSession();

        if (error) {
          throw error;
        }

        if (active) {
          setConnection({
            status: "success",
            authenticated: data.session !== null,
          });
        }
      } catch {
        if (active) {
          setConnection({ status: "error" });
        }
      }
    }

    void checkSession();

    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-50 px-6 py-16 text-zinc-950 dark:bg-zinc-950 dark:text-zinc-50">
      <section className="w-full max-w-lg rounded-md border border-zinc-200 bg-white p-8 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
        <h1 className="text-2xl font-semibold">Supabase connection test</h1>

        <div className="mt-6 space-y-2 text-sm">
          {connection.status === "checking" && (
            <p className="text-zinc-600 dark:text-zinc-400">
              Checking connection...
            </p>
          )}

          {connection.status === "success" && (
            <>
              <p className="font-medium text-emerald-700 dark:text-emerald-400">
                Supabase connection successful
              </p>
              <p className="text-zinc-600 dark:text-zinc-400">
                {connection.authenticated
                  ? "Session: authenticated"
                  : "Session: null"}
              </p>
            </>
          )}

          {connection.status === "error" && (
            <p className="font-medium text-red-700 dark:text-red-400">
              Supabase connection failed
            </p>
          )}
        </div>
      </section>
    </main>
  );
}
