"""Parse a constrained natural-language strategy without running a backtest."""

from __future__ import annotations

import argparse
import json
import sys

from pydantic import ValidationError

from app.services.strategy_interpretation import interpret_strategy
from app.services.strategy_parser import OpenAIStrategyParser, StrategyParserError
from app.services.strategy_semantics import StrategyValidationError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", required=True, help="Natural-language strategy description")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = OpenAIStrategyParser.from_settings().parse(args.strategy)
    except (StrategyParserError, StrategyValidationError, ValidationError) as error:
        print(f"Strategy parsing failed: {error}", file=sys.stderr)
        return 1

    print("Normalized strategy JSON:")
    print(json.dumps(result.specification.model_dump(mode="json"), indent=2, sort_keys=True))
    print()
    print("Defaults applied:")
    print(json.dumps([item.model_dump(mode="json") for item in result.defaults_applied], indent=2))
    print()
    print("Assumptions made:")
    print(json.dumps([item.model_dump(mode="json") for item in result.assumptions], indent=2))
    print()
    print(f"Confirmation required: {'Yes' if result.requires_confirmation else 'No'}")
    print()
    print(interpret_strategy(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
