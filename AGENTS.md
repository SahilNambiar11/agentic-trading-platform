# Agentic Trading Platform

## Product Goal

Build a web application that converts natural-language trading strategies into
validated, deterministic backtests.

The application is educational and research-oriented.
It does not execute live trades or provide financial advice.

---

## Tech Stack

Frontend
- Next.js (App Router)
- TypeScript
- Tailwind CSS
- Auth.js
- Recharts

Backend
- FastAPI
- Python 3.12
- SQLAlchemy 2
- Alembic
- PostgreSQL
- Pydantic v2

Deployment
- Frontend: Vercel
- Backend: Docker
- Database: PostgreSQL

---

## Core Workflow

1. User signs in with Google.
2. User enters a natural-language strategy.
3. LLM converts it into a constrained JSON schema.
4. Backend validates the schema.
5. User confirms assumptions.
6. Deterministic backtesting engine runs.
7. Performance metrics are calculated.
8. LLM explains results.
9. Strategy and results are saved.

---

## Engineering Principles

Never execute model-generated Python.

Never execute arbitrary code.

Backtests must always be deterministic.

Prevent look-ahead bias.

Validate every strategy with Pydantic.

Never silently assume missing parameters.

Unknown indicators should return validation errors.

Authentication must always be enforced server-side.

Never trust a user_id sent from the frontend.

Prefer small, composable modules.

---

## MVP Scope

Supported:

- SPY
- Daily candles
- SMA
- EMA
- RSI
- Long-only
- Transaction fees
- Slippage
- Stop loss
- Take profit

Not supported yet:

- Options
- Crypto
- Intraday data
- Live trading
- Portfolio optimization

---

## Development Process

Before implementing:

1. Inspect the repository.
2. Explain the implementation plan.
3. Identify affected files.
4. Wait for approval.

After implementing:

- Run lint
- Run tests
- Explain changes
- Note remaining limitations

Never claim tests passed unless they were actually run.