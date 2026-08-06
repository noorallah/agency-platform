"""API routes for enterprise global search."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database.dependencies import get_db
from app.core.openapi import STANDARD_ERROR_RESPONSES
from app.core.responses.models import ApiResponse
from app.core.security.authorization import Principal, require_authenticated
from app.search.schemas import SearchCategory, SearchResultPage
from app.search.services import SearchService

router = APIRouter(
    prefix="/api/v1/search",
    tags=["Global Search"],
    responses=STANDARD_ERROR_RESPONSES,
)

SearchPrincipal = Annotated[Principal, Depends(require_authenticated())]


@router.get("", response_model=ApiResponse[SearchResultPage])
def global_search(
    query: str,
    principal: SearchPrincipal,
    category: SearchCategory = "all",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    entity_types: str | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
) -> ApiResponse[SearchResultPage]:
    requested_types = (
        {entry.strip() for entry in entity_types.split(",") if entry.strip()}
        if entity_types
        else None
    )
    return ApiResponse(
        data=SearchService(db).search(
            query=query,
            principal=principal,
            category=category,
            page=page,
            page_size=page_size,
            entity_types=requested_types,
            include_deleted=include_deleted,
        )
    )
