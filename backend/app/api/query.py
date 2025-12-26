from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.query import get_query_service
from app.config import get_settings

router = APIRouter(prefix="/query", tags=["query"])
settings = get_settings()


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
    # Validate question length
    if len(query.question.strip()) < 3:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_REQUEST", "message": "Question too short"},
        )

    # Get request metadata
    origin = request.headers.get("origin")
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None

    query_service = get_query_service()

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
