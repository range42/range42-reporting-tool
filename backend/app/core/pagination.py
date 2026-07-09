from dataclasses import dataclass

from fastapi import Query


@dataclass
class PageParams:
    page: int
    per_page: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    @property
    def limit(self) -> int:
        return self.per_page


def page_params(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
) -> PageParams:
    """FastAPI dependency yielding validated pagination params (page>=1, 1<=per_page<=100)."""
    return PageParams(page=page, per_page=per_page)
