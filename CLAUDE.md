# CLAUDE.md

This is a polyglot monorepo for the `range42-reporting-tool`: a web application for managing, writing, and evaluating reports during cyber-range exercises. The stack is Python 3.12 / FastAPI / SQLAlchemy 2.0 async / Postgres 16 (backend) and Vue 3 / TypeScript / Vite / Tailwind v4 + DaisyUI v5 (frontend), with Docker Compose for orchestration and Caddy as the reverse proxy. Task runner is `just`; pre-commit hooks are managed by lefthook; commits must follow Conventional Commits (enforced by commitlint).

Always run `just lint && just test` before pushing.
