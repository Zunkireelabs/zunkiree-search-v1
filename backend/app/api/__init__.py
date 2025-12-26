from app.api.query import router as query_router
from app.api.widget import router as widget_router
from app.api.admin import router as admin_router

__all__ = [
    "query_router",
    "widget_router",
    "admin_router",
]
