import { getApiBaseUrl } from "@/lib/api/config";
import { createClient } from "@/lib/supabase/client";

import type {
  CreateStrategyRequest,
  ConfirmedStrategySaveRequest,
  Strategy,
  StrategyJson,
  StrategyPreview,
  UpdateStrategyRequest,
} from "./types";

export class StrategyApiError extends Error {
  // Custom error type lets React UI distinguish expected API failures from
  // unknown JavaScript exceptions and show better user-facing messages.
  constructor(message: string) {
    super(message);
    this.name = "StrategyApiError";
  }
}

function isStrategyJson(value: unknown): value is StrategyJson {
  // Runtime guard for JSON object values returned by the backend.
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStrategy(value: unknown): value is Strategy {
  // Runtime guard for the backend response shape. This catches accidental API
  // contract changes before invalid data reaches React components.
  if (!isStrategyJson(value)) {
    return false;
  }

  return (
    typeof value.id === "string" &&
    typeof value.name === "string" &&
    typeof value.source_text === "string" &&
    (value.strategy_json === null || isStrategyJson(value.strategy_json)) &&
    typeof value.created_at === "string" &&
    typeof value.updated_at === "string"
  );
}

async function getAccessToken(): Promise<string> {
  // FastAPI does not read Supabase cookies directly. The frontend pulls the
  // current browser session token and sends it as an Authorization header.
  const supabase = createClient();
  const { data, error } = await supabase.auth.getSession();

  if (error) {
    throw new StrategyApiError("Unable to verify your session. Please sign in again.");
  }

  if (!data.session?.access_token) {
    throw new StrategyApiError("Your session has expired. Please sign in again.");
  }

  return data.session.access_token;
}

async function readErrorMessage(response: Response): Promise<string> {
  // Prefer FastAPI's structured `detail` message, then fall back to safe generic
  // copy so implementation details do not leak into the UI.
  try {
    const body: unknown = await response.json();
    if (isStrategyJson(body) && typeof body.detail === "string") {
      return body.detail;
    }
  } catch {
    // Fall through to a safe status-specific message.
  }

  if (response.status === 401) {
    return "Your session has expired. Please sign in again.";
  }

  if (response.status >= 500) {
    return "The strategy service is unavailable. Please try again shortly.";
  }

  return "Unable to complete that strategy request. Please try again.";
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  // Shared request wrapper for every strategy endpoint. This is the exact point
  // where browser actions become authenticated FastAPI requests.
  const accessToken = await getAccessToken();

  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${accessToken}`,
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...init.headers,
      },
    });
  } catch {
    throw new StrategyApiError(
      "Unable to reach the strategy service. Check your connection and try again.",
    );
  }

  if (!response.ok) {
    throw new StrategyApiError(await readErrorMessage(response));
  }

  return response;
}

async function readStrategy(response: Response): Promise<Strategy> {
  // Parse and validate endpoints that should return a single strategy object.
  let body: unknown;

  try {
    body = await response.json();
  } catch {
    throw new StrategyApiError("The strategy service returned an invalid response.");
  }

  if (!isStrategy(body)) {
    throw new StrategyApiError("The strategy service returned an invalid response.");
  }

  return body;
}

export async function listStrategies(): Promise<Strategy[]> {
  // Load all strategies visible to the authenticated user.
  const response = await request("/strategies");

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new StrategyApiError("The strategy service returned an invalid response.");
  }

  if (!Array.isArray(body) || !body.every(isStrategy)) {
    throw new StrategyApiError("The strategy service returned an invalid response.");
  }

  return body;
}

export async function createStrategy(payload: CreateStrategyRequest): Promise<Strategy> {
  // Save a new natural-language strategy draft.
  return readStrategy(
    await request("/strategies", {
      body: JSON.stringify(payload),
      method: "POST",
    }),
  );
}

export async function updateStrategy(
  strategyId: string,
  payload: UpdateStrategyRequest,
): Promise<Strategy> {
  // Patch only changed user-editable fields on a saved strategy.
  return readStrategy(
    await request(`/strategies/${strategyId}`, {
      body: JSON.stringify(payload),
      method: "PATCH",
    }),
  );
}

export async function deleteStrategy(strategyId: string): Promise<void> {
  // Delete a saved strategy. A 204 response has no JSON body to parse.
  await request(`/strategies/${strategyId}`, { method: "DELETE" });
}

function isStrategyPreview(value: unknown): value is StrategyPreview {
  if (!isStrategyJson(value) || !isStrategyJson(value.parsed_strategy) || !isStrategyJson(value.backtest)) {
    return false;
  }
  const parsed = value.parsed_strategy;
  const backtest = value.backtest;
  return (
    isStrategyJson(parsed.specification) &&
    Array.isArray(parsed.defaults_applied) &&
    Array.isArray(parsed.assumptions) &&
    typeof parsed.requires_confirmation === "boolean" &&
    typeof parsed.original_text === "string" &&
    typeof parsed.interpretation === "string" &&
    typeof backtest.symbol === "string" &&
    typeof backtest.interval === "string" &&
    typeof backtest.start_date === "string" &&
    typeof backtest.end_date === "string" &&
    typeof backtest.bar_count === "number" &&
    typeof backtest.trade_count === "number"
  );
}

export async function previewStrategy(text: string): Promise<StrategyPreview> {
  const response = await request("/strategies/preview", {
    body: JSON.stringify({ text }),
    method: "POST",
  });
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new StrategyApiError("The strategy service returned an invalid preview.");
  }
  if (!isStrategyPreview(body)) {
    throw new StrategyApiError("The strategy service returned an invalid preview.");
  }
  return body;
}

export async function saveConfirmedStrategy(
  payload: ConfirmedStrategySaveRequest,
): Promise<Strategy> {
  return readStrategy(
    await request("/strategies/confirmed", {
      body: JSON.stringify(payload),
      method: "POST",
    }),
  );
}
