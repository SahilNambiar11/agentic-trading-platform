export type StrategyJson = Record<string, unknown>;

export type Strategy = {
  id: string;
  name: string;
  source_text: string;
  strategy_json: StrategyJson | null;
  created_at: string;
  updated_at: string;
};

export type CreateStrategyRequest = {
  name: string;
  source_text: string;
  strategy_json: null;
};

export type UpdateStrategyRequest = {
  name?: string;
  source_text?: string;
};
