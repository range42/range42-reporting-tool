"""Section-content discriminated union.

A tagged union keyed on ``kind``, so both the OpenAPI schema and the generated TypeScript
carry a real discriminator. Report-section bodies follow this pattern.
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
