from fastapi import APIRouter

# Reserved, intentionally empty routers — one per deferred endpoint group.
GROUPS = [
    "templates",
    "reports",
    "scoring",
    "search",
    "api_keys",
    "exports",
    "webhooks",
    "ai",
]

routers: dict[str, APIRouter] = {name: APIRouter(tags=[name]) for name in GROUPS}
