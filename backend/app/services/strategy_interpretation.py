from app.schemas.strategy_spec import (
    AppliedDefault,
    Condition,
    IndicatorOperand,
    Operand,
    ParsedStrategyResult,
    PriceOperand,
)


def interpret_strategy(result: ParsedStrategyResult) -> str:
    specification = result.specification
    lines = [
        "Interpreted strategy:",
        f"Buy {specification.symbol} when {format_condition(specification.entry)}.",
        f"Sell when {format_condition(specification.exit)}.",
        f"Risk controls: {format_risk_controls(result)}",
        "",
        "Platform defaults applied:",
    ]
    lines.extend(f"- {format_default(default)}" for default in result.defaults_applied)
    if not result.defaults_applied:
        lines.append("- None.")

    lines.extend(["", "Assumptions made:"])
    lines.extend(f"- {assumption.reason}" for assumption in result.assumptions)
    if not result.assumptions:
        lines.append("- None.")

    lines.extend(["", f"Confirmation required: {'Yes' if result.requires_confirmation else 'No'}"])
    return "\n".join(lines)


def format_risk_controls(result: ParsedStrategyResult) -> str:
    specification = result.specification
    controls: list[str] = []
    if specification.stop_loss_percent is not None:
        controls.append(f"{specification.stop_loss_percent:g}% stop loss")
    if specification.take_profit_percent is not None:
        controls.append(f"{specification.take_profit_percent:g}% take profit")
    if not controls:
        return "None."
    return f"Use {' and '.join(controls)} relative to the entry fill price."


def format_condition(condition: Condition) -> str:
    operator = condition.operator.value.replace("_", " ")
    return f"{format_operand(condition.left)} {operator} {format_operand(condition.right)}"


def format_operand(operand: Operand) -> str:
    if isinstance(operand, IndicatorOperand):
        return f"the {operand.period}-day {operand.name.value.upper()} of {operand.source}"
    if isinstance(operand, PriceOperand):
        return operand.source
    return str(operand.value)


def format_default(default: AppliedDefault) -> str:
    labels = {
        "symbol": "Symbol: SPY",
        "interval": "Daily bars",
        "execution.direction": "Long-only",
        "execution.position_size_percent": "Use 100% of available cash",
        "execution.signal_execution": "Execute on the next available trading day's open",
    }
    return labels.get(default.field, f"{default.field}: {default.value}")
