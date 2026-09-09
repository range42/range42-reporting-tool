# range42-reporting-tool

Platform-agnostic web app for managing, writing, and evaluating reports during cyber-range exercises.
See design docs in `docs/` for the pointer to CONCEPT/ARCHITECTURE.

## Quickstart (dev)

```bash
cp deploy/.env.example deploy/.env   # then edit secrets
just up
just seed
```

Then log in once as each persona through the IdP (below) and run:

```bash
just seed-grants   # assigns roles + team membership, matched by email
```

`seed-grants` is idempotent and reports anyone who has not logged in yet as
skipped, so re-run it as more personas appear.

Frontend on <http://localhost:5173>, API on <http://localhost:8000>, IdP on
<http://localhost:5556/dex>.

## Dev identity provider

`just up` includes `deploy/docker-compose.dev.yml`, which runs [Dex] as a local
OIDC provider. It is dev-only: the prod overlay never loads that file, publishes
no IdP port, and leaves `OIDC_*` blank in `deploy/.env.example`.

**One hostname, both sides.** The backend fetches OIDC discovery at boot from
inside the compose network, while the login redirect is followed by the browser,
and the `iss` claim has to match on both — so `OIDC_ISSUER_URL` and Dex's
`issuer` must name a host that resolves in both places. The overlay uses `dex`,
which compose DNS resolves in-network; making the same name reach the published
port from a browser depends on where that browser runs.

Sign in with any of these (password `changeme` for all):

| Login | Intended role |
|-------|---------------|
| `admin@range42.local` | Global Admin |
| `alice@range42.local` | Writer |
| `bob@range42.local` | Approver |
| `carol@range42.local` | Evaluator |
| `dave@range42.local` | Observer |

The **emergency admin** is a separate break-glass path that does not involve the
IdP: set `EMERGENCY_ADMIN_ENABLED=true` plus a bcrypt hash in
`EMERGENCY_ADMIN_PASSWORD_HASH`, then use the password field on the login page.
Keep it working — it is how you get in when the IdP does not come up.

Editing `deploy/dex/config.yaml` requires `docker compose ... restart dex`; it is
a bind mount and Dex only reads it at startup.

[Dex]: https://dexidp.io/
