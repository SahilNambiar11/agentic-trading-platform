# Repository Guidelines

## Project Structure & Module Organization

This repository is organized as a small full-stack workspace. The active app is in `frontend/`, a Next.js project using the App Router. Route files live under `frontend/app/`, global styles are in `frontend/app/globals.css`, and static assets are in `frontend/public/`. Frontend configuration is kept at the project root of `frontend/` (`next.config.ts`, `tsconfig.json`, `eslint.config.mjs`, `postcss.config.mjs`). The `backend/` directory currently exists but has no implementation files; add backend code there when server-side services are introduced.

For frontend changes, also read `frontend/AGENTS.md`; it notes that this Next.js version may differ from older conventions.

## Build, Test, and Development Commands

Run frontend commands from `frontend/`:

- `npm install` installs dependencies from `package-lock.json`.
- `npm run dev` starts the Next.js development server.
- `npm run build` creates a production build.
- `npm start` serves the production build after `npm run build`.
- `npm run lint` runs ESLint with Next.js core web vitals and TypeScript rules.

There are no root-level scripts yet. Add them only if they coordinate multiple packages.

## Coding Style & Naming Conventions

Use TypeScript and React function components for frontend code. Follow the existing style: two-space indentation, double quotes, semicolons, and Tailwind utility classes for styling. Name React components in `PascalCase`, functions and variables in `camelCase`, and route directories in lowercase path-oriented names. Keep shared UI or utility code close to where it is used until reuse is clear.

## Testing Guidelines

No test framework is configured yet. When adding tests, colocate them with the code they cover or place broader integration tests in a clearly named `tests/` directory within the relevant package. Use names such as `component.test.tsx` or `service.test.ts`. Until tests exist, run `npm run lint` and `npm run build` before submitting frontend changes.

## Commit & Pull Request Guidelines

This repository has no existing commit history, so use concise imperative commit messages such as `Add dashboard shell` or `Configure linting`. Pull requests should include a short summary, testing performed, and screenshots for visible UI changes. Link related issues when available and call out configuration or environment changes explicitly.

## Security & Configuration Tips

Do not commit secrets or local environment files. Prefer `.env.local` for machine-specific frontend settings and document required variables in README files or example env files.
