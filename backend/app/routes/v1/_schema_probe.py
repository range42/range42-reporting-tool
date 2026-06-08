"""SCAFFOLDING — throwaway route that forces the SectionBody discriminated union
into the OpenAPI schema (and thus into the generated frontend types).

Exists only so ``openapi-typescript`` emits the discriminated union. Safe to
delete once a real WP3 route consumes ``SectionBody``; the schema + generated
type are the durable artifacts, not this endpoint.
"""

from fastapi import APIRouter

from app.schemas.common import DataEnvelope
from app.schemas.section_content import SectionBody

router = APIRouter()


@router.post("/_schema_probe")
async def schema_probe(body: SectionBody) -> DataEnvelope[SectionBody]:
    """Echo the discriminated-union body. SCAFFOLDING — see module docstring."""
    return DataEnvelope(data=body)
