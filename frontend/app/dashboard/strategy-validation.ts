export type StrategyInput = {
  name: string;
  sourceText: string;
};

export type StrategyInputValidationResult =
  | { valid: true; value: StrategyInput }
  | { valid: false; error: string };

export function validateStrategyInput(
  name: string,
  sourceText: string,
): StrategyInputValidationResult {
  // Normalize and validate in one place so create and edit flows behave the
  // same way before the request reaches the backend's stricter Pydantic models.
  const normalizedName = name.trim();
  const normalizedSourceText = sourceText.trim();

  if (!normalizedName || !normalizedSourceText) {
    return { valid: false, error: "Enter both a strategy name and description." };
  }

  if (normalizedName.length > 200) {
    return { valid: false, error: "Strategy names must be 200 characters or fewer." };
  }

  return {
    valid: true,
    value: { name: normalizedName, sourceText: normalizedSourceText },
  };
}
