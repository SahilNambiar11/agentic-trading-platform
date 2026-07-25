import { getApiBaseUrl } from "@/lib/api/config";
import { createClient } from "@/lib/supabase/client";

import type {
  CreateStrategyRequest,
  ConfirmedStrategySaveRequest,
  PreviewEnqueueResponse,
  PreviewJob,
  PreviewJobStage,
  PreviewJobStatus,
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
  if (
    !isStrategyJson(value) ||
    !isStrategyJson(value.parsed_strategy) ||
    !isStrategyJson(value.backtest)
  ) {
    return false;
  }
  const parsed = value.parsed_strategy;
  const backtest = value.backtest;
  const numberLike = (item: unknown) =>
    (typeof item === "number" && Number.isFinite(item)) ||
    (typeof item === "string" && item.trim() !== "" && Number.isFinite(Number(item)));
  const exitReasons = new Set([
    "strategy_exit",
    "stop_loss",
    "take_profit",
    "final_liquidation",
  ]);
  const isEquityPoint = (item: unknown) =>
    isStrategyJson(item) &&
    typeof item.timestamp === "string" &&
    numberLike(item.strategy_value) &&
    numberLike(item.buy_and_hold_value);
  const isPricePoint = (item: unknown) =>
    isStrategyJson(item) &&
    typeof item.timestamp === "string" &&
    numberLike(item.close_price);
  const isTrade = (item: unknown) =>
    isStrategyJson(item) &&
    typeof item.signal_timestamp === "string" &&
    typeof item.entry_timestamp === "string" &&
    numberLike(item.entry_price) &&
    Number.isInteger(item.quantity) &&
    (item.exit_signal_timestamp === null ||
      typeof item.exit_signal_timestamp === "string") &&
    typeof item.exit_timestamp === "string" &&
    numberLike(item.exit_price) &&
    numberLike(item.profit_loss) &&
    numberLike(item.return_percentage) &&
    typeof item.exit_reason === "string" &&
    exitReasons.has(item.exit_reason);
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
    typeof backtest.trade_count === "number" &&
    Array.isArray(backtest.equity_curve) &&
    backtest.equity_curve.every(isEquityPoint) &&
    Array.isArray(backtest.price_series) &&
    backtest.price_series.every(isPricePoint) &&
    Array.isArray(backtest.trades) &&
    backtest.trades.every(isTrade)
  );
}

function isPreviewEnqueueResponse(value: unknown): value is PreviewEnqueueResponse {
  return (
    isStrategyJson(value) &&
    typeof value.job_id === "string" &&
    value.job_id.length > 0 &&
    value.status === "queued"
  );
}

const JOB_STATUSES = new Set<PreviewJobStatus>(["queued", "running", "completed", "failed"]);
const JOB_STAGES = new Set<PreviewJobStage>([
  "queued",
  "parsing",
  "validating",
  "compiling",
  "loading_data",
  "backtesting",
  "generating_results",
  "completed",
  "failed",
]);

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isPreviewJob(value: unknown): value is PreviewJob {
  if (!isStrategyJson(value)) {
    return false;
  }

  const status = value.status;
  const previewResult = value.preview_result;
  return (
    typeof value.id === "string" &&
    typeof status === "string" &&
    JOB_STATUSES.has(status as PreviewJobStatus) &&
    typeof value.stage === "string" &&
    JOB_STAGES.has(value.stage as PreviewJobStage) &&
    Number.isInteger(value.progress) &&
    typeof value.progress === "number" &&
    value.progress >= 0 &&
    value.progress <= 100 &&
    typeof value.created_at === "string" &&
    isNullableString(value.started_at) &&
    isNullableString(value.completed_at) &&
    isNullableString(value.error) &&
    (status === "completed"
      ? isStrategyPreview(previewResult)
      : previewResult === null)
  );
}

async function readJson(response: Response, invalidMessage: string): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    throw new StrategyApiError(invalidMessage);
  }
}

export async function enqueueStrategyPreview(
  text: string,
  signal?: AbortSignal,
): Promise<PreviewEnqueueResponse> {
  const response = await request("/strategies/preview", {
    body: JSON.stringify({ text }),
    method: "POST",
    signal,
  });
  const body = await readJson(
    response,
    "The strategy service returned an invalid preview job response.",
  );
  if (!isPreviewEnqueueResponse(body)) {
    throw new StrategyApiError(
      "The strategy service returned an invalid preview job response.",
    );
  }
  return body;
}

export async function getPreviewJob(
  jobId: string,
  signal?: AbortSignal,
): Promise<PreviewJob> {
  const response = await request(`/jobs/${encodeURIComponent(jobId)}`, { signal });
  const body = await readJson(
    response,
    "The strategy service returned an invalid preview job.",
  );
  if (!isPreviewJob(body)) {
    throw new StrategyApiError("The strategy service returned an invalid preview job.");
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
