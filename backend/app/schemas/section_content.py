"""Section-content discriminated union (worked example / shape reservation).

This is the one real Pydantic discriminated union in the skeleton. It locks the
pattern WP3+ report-section bodies follow: a tagged union keyed on ``kind`` so
both the OpenAPI schema and the generated TypeScript carry a real discriminator.
Domain fields firm up in WP3; the union *shape* is reserved now.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class RichTextBody(BaseModel):
    kind: Literal["rich_text"] = "rich_text"
    content: str


class ChoiceBody(BaseModel):
    kind: Literal["choice"] = "choice"
    choice_values: list[str]


SectionBody = Annotated[RichTextBody | ChoiceBody, Field(discriminator="kind")]
