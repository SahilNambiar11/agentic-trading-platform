import { createBrowserClient } from "@supabase/ssr";

export function createClient() {
  // This client runs in the browser. It can read the user's Supabase session and
  // provide the access token that frontend API helpers attach to FastAPI calls.
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl || !supabaseAnonKey) {
    throw new Error("Missing required Supabase public environment variables.");
  }

  return createBrowserClient(supabaseUrl, supabaseAnonKey);
}
