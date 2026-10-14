"""AUTO_CREATE_TABLES gates Base.metadata.create_all() at startup. Default on keeps today's behavior."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app import main
from app.config import Settings


def test_default_is_on_so_existing_deploys_are_unchanged():
    assert Settings.model_fields["auto_create_tables"].default is True


async def _run_startup(flag: bool) -> AsyncMock:
    init = AsyncMock()
    fake = SimpleNamespace(auto_create_tables=flag, enable_inbound_dispatcher=False)
    app = SimpleNamespace(state=SimpleNamespace())
    with patch.object(main, "init_db", init), patch.object(main, "settings", fake):
        cm = main.lifespan(app)
        try:
            await cm.__aenter__()
        except Exception:
            pass  # only the create_all decision matters here; later startup steps are out of scope
        else:
            await cm.__aexit__(None, None, None)
    return init


@pytest.mark.asyncio
async def test_create_all_runs_when_enabled():
    init = await _run_startup(True)
    init.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_all_is_skipped_when_disabled():
    init = await _run_startup(False)
    init.assert_not_awaited()
