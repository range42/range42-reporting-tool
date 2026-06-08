# Contributing

## Branch Model

- `main` — stable, always deployable
- `dev` — integration branch for in-progress work
- `feature/<description>` — feature branches, PR into `dev`
- `fix/<description>` — bug fix branches, PR into `dev`

## Commit Style

This project uses [Conventional Commits](https://www.conventionalcommits.org/). Examples:

```
feat(backend): add report export endpoint
fix(frontend): correct branding color application
chore: update dependencies
docs: add deployment guide
```

## Development Workflow

1. Fork / branch from `dev`
2. Run `just lint` before pushing — all lint checks must pass
3. Run `just test` before pushing — all tests must pass
4. Open a PR into `dev`

## Code Quality

```bash
just lint   # runs ruff + mypy (backend) and eslint + prettier (frontend)
just test   # runs pytest (backend) and vitest (frontend)
```

Lefthook runs lint automatically on pre-commit and commitlint on commit-msg.
