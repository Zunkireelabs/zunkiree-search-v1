"""Browser-side origin control for the education endpoints.

A browser always sends the embedding website in the Origin header, so a website that is not on the tenant's approved list
(the `domains` table, checked by QueryService._validate_origin) is refused. A request with no Origin header (server to
server, same origin) is let through, exactly as on the other chat paths: this keeps other websites from using a tenant's
chatbot, it is not authentication.
"""
from fastapi import HTTPException


async def require_allowed_origin(request, db, customer_id, query_service) -> None:
    origin = request.headers.get("origin") if request is not None else None
    if origin and not await query_service._validate_origin(db, customer_id, origin):
        raise HTTPException(
            status_code=403,
            detail={"code": "ORIGIN_NOT_ALLOWED", "message": "Origin domain not allowed"},
        )
