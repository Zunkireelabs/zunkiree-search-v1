"""History restore endpoint: education tenants only; everyone else gets an empty list."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.widget import get_widget_history


def _db_returning(customer):
    result = MagicMock()
    result.scalar_one_or_none.return_value = customer
    return SimpleNamespace(execute=AsyncMock(return_value=result))


@pytest.mark.asyncio
async def test_unknown_site_is_404():
    with pytest.raises(HTTPException) as e:
        await get_widget_history("nope", "s1", _db_returning(None))
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_non_education_tenant_gets_empty_history():
    out = await get_widget_history("shop", "s1", _db_returning(SimpleNamespace(id="c", website_type="ecommerce")))
    assert out == {"messages": []}


@pytest.mark.asyncio
async def test_education_tenant_gets_stored_messages_and_profile_progress():
    msgs = [{"id": "1", "role": "assistant", "content": "hi", "blocks": [{"type": "choice_cards"}], "created_at": "t"}]
    profile = {"countries": ["uk"], "budget": 30000, "contact": {}, "shown": {}}
    with patch("app.services.education_memory.DbEducationMemory.list_messages", AsyncMock(return_value=msgs)), \
         patch("app.services.education_memory.DbEducationMemory.load_profile", AsyncMock(return_value=profile)):
        out = await get_widget_history("edu", "s1", _db_returning(SimpleNamespace(id="c", website_type="education")))
    assert out == {"messages": msgs, "profile_progress": {"filled": 2, "total": 6}}
