export type StrategyJson = Record<string, unknown>;

export type StrategyAssumption = {
  field: string;
  inferred_value: unknown;
  reason: string;
  confidence: "high" | "medium" | "low";
  requires_confirmation: true;
};

export type AppliedDefault = { field: string; value: unknown; reason: string };

export type StrategyPreview = {
  parsed_strategy: {
    specification: StrategyJson;
    defaults_applied: AppliedDefault[];
    assumptions: StrategyAssumption[];
    requires_confirmation: boolean;
    original_text: string;
    interpretation: string;
  };
  backtest: {
    symbol: string;
    interval: string;
    start_date: string;
    end_date: string;
    bar_count: number;
    starting_cash: string | number;
    ending_value: string | number;
    total_return_percent: string | number;
    cagr_percent: string | number | null;
    max_drawdown_percent: string | number;
    trade_count: number;
    win_rate_percent: string | number;
    buy_and_hold_return_percent: string | number;
  };
};

// Mirrors the backend StrategyResponse schema. Keeping this shape explicit
// makes frontend API validation and component props easier to reason about.
export type Strategy = {
  id: string;
  name: string;
  source_text: string;
  strategy_json: StrategyJson | null;
  created_at: string;
  updated_at: string;
};

export type CreateStrategyRequest = {
  // The current UI creates unparsed strategy drafts, so strategy_json is always
  // null here. Future LLM parsing can broaden this request type.
  name: string;
  source_text: string;
  strategy_json: null;
};

export type UpdateStrategyRequest = {
  // Only user-editable fields are exposed. The frontend never sends id/user_id.
  name?: string;
  source_text?: string;
};

export type ConfirmedStrategySaveRequest = {
  name: string;
  source_text: string;
  specification: StrategyJson;
  defaults_applied: AppliedDefault[];
  assumptions: StrategyAssumption[];
  requires_confirmation: boolean;
  confirmed: true;
};
