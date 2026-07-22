# Supabase Authentication Infrastructure Review

This guide reviews the initial Supabase authentication plumbing in the Next.js 16 frontend. It establishes browser and server clients, refreshes cookie-based sessions at the request boundary, and provides a temporary connection test. Login, signup, protected routes, and product authorization are not implemented yet.

## `lib/supabase/client.ts`

```ts
import { createBrowserClient } from "@supabase/ssr";

export function createClient() {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl || !supabaseAnonKey) {
    throw new Error("Missing required Supabase public environment variables.");
  }

  return createBrowserClient(supabaseUrl, supabaseAnonKey);
}
```

### Purpose

This is the shared factory for Supabase clients used by Client Components. It reads the public project configuration, validates it, and returns an SSR-compatible browser client.

### Important sections

- `NEXT_PUBLIC_SUPABASE_URL` identifies the Supabase endpoint.
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` is the public anonymous credential used by browser requests.
- The explicit check fails early rather than building a broken client or silently selecting a fallback project.
- `createBrowserClient` configures browser session storage compatible with the server-side clients.

Constructing the client is synchronous and does not contact Supabase. Network activity begins when a caller invokes an API such as `auth.getSession()` or a future sign-in method.

### Connections, security, and boilerplate

`app/auth-test/page.tsx` currently calls this function. Future login, signup, logout, and browser-side account controls can use it too. It is separate from `server.ts` because browser and server runtimes access cookies differently.

The URL and anonymous key are intentionally visible in browser JavaScript. They are not administrative credentials; Row Level Security must restrict their access. A service-role key must never be passed here or stored in a `NEXT_PUBLIC_` variable.

The validation and wrapper are ordinary project logic. `createBrowserClient` and its session behavior are Supabase boilerplate.

## `lib/supabase/server.ts`

```ts
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

export async function createClient() {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl || !supabaseAnonKey) {
    throw new Error("Missing required Supabase public environment variables.");
  }

  const cookieStore = await cookies();

  return createServerClient(supabaseUrl, supabaseAnonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) => {
            cookieStore.set(name, value, options);
          });
        } catch {
          // Server Components cannot write cookies; proxy.ts handles refreshes.
        }
      },
    },
  });
}
```

### Purpose

This factory creates a Supabase client for Server Components, Server Actions, and Route Handlers. It is scoped to the current request and uses that request's cookies to act as the current user.

### Important sections

- `await cookies()` gets the current Next.js request's cookie store. Current Next.js request APIs are asynchronous.
- `getAll()` lets `@supabase/ssr` recover a potentially chunked Supabase session without application code depending on internal cookie names.
- `setAll()` applies session-cookie changes where the current server context permits mutation.
- The `catch` handles the expected limitation that Server Components can read cookies but cannot write them. The request proxy performs reliable refresh and response writes.

The client must be created per request. A global instance could retain one user's cookie context and expose it to another request.

### Connections, security, and boilerplate

No route calls this factory yet. Future server-rendered pages and handlers will use it. It consumes session state kept current by `lib/supabase/proxy.ts` and uses the same project configuration as the browser client.

The anonymous key preserves RLS enforcement. It must not be replaced with a service-role key for ordinary user requests. Sensitive server code should validate identity with an appropriate verified-auth method rather than trusting a browser-supplied user ID or treating `getSession()` alone as authorization.

Configuration validation is project logic. The `cookies()` adapter and `getAll`/`setAll` structure are Next.js and Supabase boilerplate.

## `proxy.ts`

```ts
import type { NextRequest } from "next/server";

import { updateSession } from "@/lib/supabase/proxy";

export async function proxy(request: NextRequest) {
  return updateSession(request);
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
```

### Purpose

This is the convention-based Next.js 16 request entry point. Next.js invokes `proxy()` before matched routes and passes the request to the Supabase session-refresh helper.

### Important sections

- `proxy()` returns the exact response from `updateSession`, including refreshed cookies and headers.
- `config.matcher` covers application routes while excluding build assets, image optimization, the favicon, and common image files. Those resources do not need authentication processing.
- `import type` keeps `NextRequest` as a compile-time type with no runtime import.

### Connections, security, and boilerplate

This file connects Next.js's request lifecycle to `lib/supabase/proxy.ts`. Without it, that helper would not run automatically and browser/server session state could diverge as tokens expire.

The proxy synchronizes authentication state; it does not make routes private. Future protected routes require explicit server checks, and database access still requires RLS. Returning a different response could discard refreshed cookies.

The thin delegation is project organization. The filename, function export, and matcher are Next.js boilerplate. Older examples use `middleware.ts`; Next.js 16 uses `proxy.ts`.

## `lib/supabase/proxy.ts`

```ts
import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

export async function updateSession(request: NextRequest) {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl || !supabaseAnonKey) {
    throw new Error("Missing required Supabase public environment variables.");
  }

  let response = NextResponse.next({ request });

  const supabase = createServerClient(supabaseUrl, supabaseAnonKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet, headers) {
        cookiesToSet.forEach(({ name, value }) => {
          request.cookies.set(name, value);
        });

        response = NextResponse.next({ request });

        cookiesToSet.forEach(({ name, value, options }) => {
          response.cookies.set(name, value, options);
        });

        Object.entries(headers).forEach(([name, value]) => {
          response.headers.set(name, value);
        });
      },
    },
  });

  await supabase.auth.getClaims();

  return response;
}
```

### Purpose

This module performs request-boundary session synchronization. It reads incoming Supabase cookies, validates the current token, and propagates refreshed state to downstream server code and the browser.

### Important sections

- `NextResponse.next({ request })` creates a response that continues to the requested route.
- `getAll()` supplies incoming cookies to Supabase.
- The first cookie loop updates `request.cookies`, making refreshed state visible to Server Components during the current request.
- The response is rebuilt using that updated request.
- The second loop writes to `response.cookies`, returning refreshed state to the browser for future requests while preserving Supabase's options.
- Supabase-provided headers are copied so the installed `@supabase/ssr` version's response and caching semantics are retained.
- `getClaims()` validates the current JWT claims and triggers session handling. Constructing a client alone does not validate the session.

Request cookies affect the current server render. Response cookies affect future browser requests. Both updates are necessary.

### Connections, security, and boilerplate

Root `proxy.ts` calls `updateSession()` for each matched request. Refreshed request state is then available to `lib/supabase/server.ts`, while outgoing cookies keep `lib/supabase/client.ts` synchronized in the browser.

`getClaims()` validates authentication but does not authorize the route. Tokens, cookies, and auth headers must never be logged. The client must remain request-scoped and use the anonymous key, not the service-role key.

Environment checks and helper organization are project logic. The cookie adapter, dual propagation, header copying, and `NextResponse` mechanics are framework/Supabase boilerplate whose ordering must be preserved.

## `app/auth-test/page.tsx`

```tsx
"use client";

import { useEffect, useState } from "react";

import { createClient } from "@/lib/supabase/client";

type ConnectionState =
  | { status: "checking" }
  | { status: "success"; authenticated: boolean }
  | { status: "error" };

export default function AuthTestPage() {
  const [connection, setConnection] = useState<ConnectionState>({
    status: "checking",
  });

  useEffect(() => {
    let active = true;

    async function checkSession() {
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
```

### Purpose

This temporary public route verifies that browser configuration exists, the browser client initializes, Supabase Auth responds, and session presence can be read.

### Important sections

- `"use client"` is required because App Router components default to Server Components, while this page uses hooks and browser APIs.
- `ConnectionState` models checking, success, and error without invalid combinations.
- The effect creates the browser client and calls `auth.getSession()` after mounting.
- A null session is a successful unauthenticated result, not a connection failure.
- The `active` flag prevents obsolete asynchronous work from updating state after effect cleanup; it does not cancel the request.
- The UI reports only session presence and never renders credentials, tokens, user data, or the session object.

### Connections, security, and boilerplate

The route uses `lib/supabase/client.ts`. Its request first passes through the root proxy, so it exercises request-boundary and browser plumbing. Removing it would remove only the diagnostic route.

`getSession()` is suitable for browser diagnostics and presentation state, but it is not sufficient authorization for sensitive server operations. Protected data must rely on validated server identity and RLS.

The state model and messages are project logic. The Client Component directive, hooks, and async effect cleanup are React/Next.js boilerplate. The session call is Supabase integration code.

## `.gitignore`

```gitignore
# See https://help.github.com/articles/ignoring-files/ for more about ignoring files.

# dependencies
/node_modules
/.pnp
.pnp.*
.yarn/*
!.yarn/patches
!.yarn/plugins
!.yarn/releases
!.yarn/versions

# testing
/coverage

# next.js
/.next/
/out/

# production
/build

# misc
.DS_Store
*.pem

# debug
npm-debug.log*
yarn-debug.log*
yarn-error.log*
.pnpm-debug.log*

# env files (can opt-in for committing if needed)
.env*
!.env.example

# vercel
.vercel

# typescript
*.tsbuildinfo
next-env.d.ts
```

### Purpose and important sections

This file keeps dependencies, generated output, logs, and machine-specific configuration out of Git. The authentication-relevant rules are `.env*`, which ignores real environment files such as `.env.local`, followed by `!.env.example`, which re-includes the safe documentation file. Order matters because Git uses the last matching rule.

`.env.local` supplies actual values to the Supabase modules, while `.env.example` documents their names. `.gitignore` is preventive repository configuration, not runtime security. It does not remove a secret already committed to history; exposed credentials must be rotated.

The environment exception is project-specific. Most other entries are ordinary Next.js and package-manager boilerplate.

## `.env.example`

```dotenv
NEXT_PUBLIC_SUPABASE_URL=your-supabase-url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-supabase-anon-key
```

### Purpose and important sections

This file documents the variables required by the browser, server, and proxy modules. It contains placeholders and is not automatically loaded. Developers put actual local values in ignored `.env.local` files.

Both names use `NEXT_PUBLIC_`, so Next.js may include their values in browser JavaScript. That is correct for the project URL and anonymous key. Database passwords, service-role keys, access tokens, and other private credentials must never appear here or use the `NEXT_PUBLIC_` prefix.

The variable names are project configuration; placeholder example files are standard project boilerplate.

## Request Flow

```text
Browser requests an application route
                |
                | sends Supabase cookies, if present
                v
        Next.js 16 proxy.ts
                |
                v
   lib/supabase/proxy.ts
   - reads request cookies
   - validates claims
   - refreshes session if needed
   - updates request cookies for this render
   - updates response cookies for the browser
                |
         +------+------+
         |             |
         v             v
 Server rendering    HTTP response
         |             |
         v             v
 lib/supabase/       Browser stores
 server.ts           refreshed cookies
         |             |
         |             v
         |       React Client Components
         |             |
         |             v
         |       lib/supabase/client.ts
         |             |
         +-------> Supabase Auth/API
                       |
                       v
                PostgreSQL with RLS
```

For an unauthenticated `/auth-test` visit, the proxy finds no valid user, the page hydrates, and browser `getSession()` returns `null`. The connection is still successful. After login is added, the browser sends session cookies, the proxy validates or refreshes them, server code sees the updated request state, and the browser receives updated cookies for later requests.

## Practical Summary

Browser and server authentication use the same Supabase project and user session but require different clients. The browser client supports interactive operations and observes browser state. The server client reads the current request's cookies and makes user-scoped server calls.

Cookies connect those runtimes. The browser sends them with requests, and the Next.js proxy validates the token before route rendering. When Supabase refreshes a session, the proxy updates request cookies so the current server render sees the new state and response cookies so the browser stores it for future requests.

This infrastructure keeps session state consistent; it does not implement authorization. Future protected routes must validate identity, and Supabase RLS must remain the final database-access boundary.
