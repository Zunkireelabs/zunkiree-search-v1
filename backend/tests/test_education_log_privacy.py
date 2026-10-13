"""Logs must not carry what a student typed or told us. Before this, the query routes logged the first 80 characters of every
question, the tool loop logged the values the AI saved to the profile (score, budget), and the server's access log recorded
the session id in /widget/history/<site>/<session> (anyone holding that id can read the whole chat). Education only: other
tenants keep their existing log lines (clinic and Instagram debugging relies on them)."""
import logging
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.query import QueryRequest, submit_query, submit_query_stream
from app.models.customer import Customer
from app.models.widget_config import WidgetConfig
from app.utils.log_redaction import (
    SessionPathRedactionFilter, install_access_log_redaction, question_for_log, redact_session_in_path,
)
from tests.test_education_agent import _catalog, _chunk, _tool_chunk, make_agent, run  # noqa: F401 (_catalog is autouse)

SECRET = "my ielts is 6.5 and my budget is 30000"
SITE = "edu-agent-test"


def _customer(website_type):
    return Customer(id=uuid.UUID("00000000-0000-0000-0000-0000000000ed"), name="Edu", site_id=SITE, api_key="k",
                    website_type=website_type)


def _agent_service():
    service = MagicMock()

    async def gen(**kw):
        yield {"type": "done", "answer": "ok", "suggestions": [], "sources": []}
    service.process_agent_stream = gen
    return service


async def _call_stream(website_type, question=SECRET):
    customer = _customer(website_type)
    request = AsyncMock()
    request.headers, request.client = {}, None
    with patch("app.api.query.get_query_service") as qs, \
         patch("app.services.education_agent.get_education_agent_service", return_value=_agent_service()), \
         patch("app.services.clinic_agent.get_clinic_agent_service", return_value=_agent_service()):
        qs.return_value._get_customer = AsyncMock(return_value=customer)
        qs.return_value._get_widget_config = AsyncMock(return_value=WidgetConfig(customer_id=customer.id, brand_name="Edu"))
        response = await submit_query_stream(request, QueryRequest(site_id=SITE, question=question, session_id="s1"), db=AsyncMock())
        "".join([c async for c in response.body_iterator])


@pytest.mark.asyncio
async def test_education_stream_route_does_not_log_the_question(caplog):
    with caplog.at_level(logging.INFO):
        await _call_stream("education")
    assert "ielts" not in caplog.text and "30000" not in caplog.text
    assert "[QUERY-STREAM]" in caplog.text and f"<{len(SECRET)} chars>" in caplog.text   # still traceable: site, channel, length


@pytest.mark.asyncio
async def test_other_tenants_keep_logging_the_question_for_debugging(caplog):
    with caplog.at_level(logging.INFO):
        await _call_stream("clinic", question="book a facial tomorrow")
    assert "book a facial tomorrow" in caplog.text


@pytest.mark.asyncio
async def test_education_non_stream_route_does_not_log_the_question(caplog):
    customer = _customer("education")
    request = AsyncMock()
    request.headers = {"origin": "https://admizz.example"}
    with patch("app.api.query.get_query_service") as qs, caplog.at_level(logging.INFO):
        qs.return_value._get_customer = AsyncMock(return_value=customer)
        qs.return_value._get_widget_config = AsyncMock(return_value=WidgetConfig(customer_id=customer.id, brand_name="Edu"))
        try:
            await submit_query(request, QueryRequest(site_id=SITE, question=SECRET, session_id="s1"), db=AsyncMock())
        except Exception:   # what happens after the log line is not what this test is about
            pass
    assert "[QUERY-TRACE]" in caplog.text
    assert "ielts" not in caplog.text and "30000" not in caplog.text


@pytest.mark.asyncio
async def test_agent_does_not_log_values_the_student_gave(caplog):
    agent = make_agent([[_tool_chunk("update_profile", {"english_score": 6.5, "budget": 30000})], [_chunk("Noted.")]])
    with caplog.at_level(logging.INFO):
        await run(agent, "i scored 6.5 in ielts and i can spend 30000 a year")   # no rule matches: the AI tool loop answers
    assert "tool=update_profile" in caplog.text            # the tool name is still logged
    assert "6.5" not in caplog.text and "30000" not in caplog.text


def test_question_for_log():
    assert question_for_log("education", "secret words") == "<12 chars>"
    assert question_for_log("clinic", "hello") == "'hello'"
    assert question_for_log("clinic", "x" * 200) == repr("x" * 80)


def test_redact_session_in_path():
    assert redact_session_in_path("/api/v1/widget/history/admizz/abc-123?x=1") == "/api/v1/widget/history/admizz/<session>?x=1"
    assert redact_session_in_path("/api/v1/query/stream") == "/api/v1/query/stream"


def test_access_log_filter_redacts_the_path_argument():
    record = logging.LogRecord("uvicorn.access", logging.INFO, "f", 1, '%s - "%s %s HTTP/%s" %d',
                               ("1.2.3.4:5", "GET", "/api/v1/widget/history/admizz/abc-123", "1.1", 200), None)
    assert SessionPathRedactionFilter().filter(record) is True
    assert "abc-123" not in record.getMessage() and "/history/admizz/<session>" in record.getMessage()


def test_access_log_filter_ignores_unexpected_records():
    record = logging.LogRecord("uvicorn.access", logging.INFO, "f", 1, "plain message", None, None)
    assert SessionPathRedactionFilter().filter(record) is True and record.getMessage() == "plain message"


def test_install_is_idempotent_and_attached_to_the_access_logger():
    install_access_log_redaction()
    install_access_log_redaction()
    filters = [f for f in logging.getLogger("uvicorn.access").filters if isinstance(f, SessionPathRedactionFilter)]
    assert len(filters) == 1
