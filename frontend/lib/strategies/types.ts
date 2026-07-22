export type StrategyJson = Record<string, unknown>;

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
