import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.query import get_query_service
from app.config import get_settings

router = APIRouter(prefix="/query", tags=["query"])
settings = get_settings()

GREETING_WORDS = {
    "hi", "hello", "hey", "yo",
    "good morning", "good afternoon",
    "good evening", "hola",
}


class QueryRequest(BaseModel):
    site_id: str = Field(..., description="Customer site identifier")
    question: str = Field(..., max_length=500, description="User question")


class SourceInfo(BaseModel):
    title: str
    url: str


class QueryResponse(BaseModel):
    answer: str
    suggestions: list[str] = []
    sources: list[SourceInfo] = []


@router.post("", response_model=QueryResponse)
async def submit_query(
    request: Request,
    query: QueryRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a question and receive an AI-generated answer.

    The answer is generated using RAG (Retrieval-Augmented Generation)
    based on the customer's indexed data.
    """
    # Validate: reject empty questions
    if not query.question or not query.question.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "EMPTY_QUESTION", "message": "Question cannot be empty"},
        )

    query_service = get_query_service()

    # Resolve tenant FIRST — greeting needs tenant context
    try:
        customer = await query_service._get_customer(db, query.site_id)
        if not customer:
            raise ValueError("Invalid site_id")
        config = await query_service._get_widget_config(db, customer.id)
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_SITE_ID", "message": str(e)},
        )

    # Handle greeting intent AFTER tenant resolution
    cleaned = query.question.lower().strip()
    if cleaned in GREETING_WORDS:
        brand_name = config.brand_name if config else customer.name
        # Use config quick_actions for greeting suggestions
        suggestions: list[str] = []
        if config and config.quick_actions:
            try:
                suggestions = json.loads(config.quick_actions)
            except (json.JSONDecodeError, TypeError):
                suggestions = []

        return QueryResponse(
            answer=f"Hi! I'm {brand_name}. How can I help you today?",
            suggestions=suggestions,
            sources=[],
        )

    # Get request metadata
    origin = request.headers.get("origin")
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None

    try:
        result = await query_service.process_query(
            db=db,
            site_id=query.site_id,
            question=query.question.strip(),
            origin=origin,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        return QueryResponse(
            answer=result["answer"],
            suggestions=result["suggestions"],
            sources=[SourceInfo(**s) for s in result["sources"]],
        )

    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_SITE_ID", "message": str(e)},
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail={"code": "INVALID_ORIGIN", "message": str(e)},
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "message": "An error occurred processing your request"},
        )
