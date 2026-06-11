from fastapi import APIRouter

# Reserved, intentionally empty routers — one per deferred endpoint group (design §8.2).
# Implemented in WP2–WP6.
GROUPS = [
    "teams",
    "roles",
    "templates",
    "reports",
    "attachments",
    "evaluations",
    "campaigns",
    "scoring",
    "search",
    "api_keys",
    "exports",
    "webhooks",
    "ai",
]

routers: dict[str, APIRouter] = {name: APIRouter(tags=[name]) for name in GROUPS}
