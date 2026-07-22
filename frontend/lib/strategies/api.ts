import { getApiBaseUrl } from "@/lib/api/config";
import { createClient } from "@/lib/supabase/client";

import type {
  CreateStrategyRequest,
  Strategy,
  StrategyJson,
  UpdateStrategyRequest,
} from "./types";

export class StrategyApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "StrategyApiError";
  }
}

function isStrategyJson(value: unknown): value is StrategyJson {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStrategy(value: unknown): value is Strategy {
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
  const supabase = createClient();
  const { data, error } = await supabase.auth.getSession();

  if (error) {
    throw new StrategyApiError("Unable to verify your session. Please sign in again.");
  }

  if (!data.session?.access_token) {
    throw new StrategyApiError("Your session has expired. Please sign in again.", 401);
  }

  return data.session.access_token;
}

async function readErrorMessage(response: Response): Promise<string> {
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
    throw new StrategyApiError(await readErrorMessage(response), response.status);
  }

  return response;
}

async function readStrategy(response: Response): Promise<Strategy> {
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
  return readStrategy(
    await request(`/strategies/${strategyId}`, {
      body: JSON.stringify(payload),
      method: "PATCH",
    }),
  );
}

export async function deleteStrategy(strategyId: string): Promise<void> {
  await request(`/strategies/${strategyId}`, { method: "DELETE" });
}
