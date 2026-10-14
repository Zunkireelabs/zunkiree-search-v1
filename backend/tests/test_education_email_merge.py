"""A typed email is not proof of identity. Before this, submitting the counselor form with an email that another session had
used copied that session's profile in: a stranger who typed a student's email then saw the student's countries, budget
and English score. The cross-device merge stays off until the email is verified. Runs with production flags (tap
validation on), so the stranger's submit comes from a lead form actually shown in the stranger's own session."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import get_settings
from app.services import education_agent
from tests.test_education_agent import _catalog, _chunk, make_agent  # noqa: F401 (_catalog is an autouse fixture)

VICTIM = {"countries": ["au"], "budget": 30000, "english_score": 6.5,
          "contact": {"name": "Asha", "email": "asha@x.com", "phone": "98111"}, "shown": {}}


async def _turn(agent, session, question, block_action=None):
    db = SimpleNamespace(commit=AsyncMock())
    return [e async for e in agent.process_agent_stream(
        db=db, site_id="edu-agent-test", session_id=session, question=question, customer_id="c",
        customer=None, config=None, brand_name="Admizz", block_action=block_action)]


async def _submit_contact(agent, session, email):
    form = next(e["block"] for e in await _turn(agent, session, "talk to a counselor")
                if e["type"] == "ui_block" and e["block"]["type"] == "lead_form")
    await _turn(agent, session, "sent", {"blockId": form["block_id"], "blockType": "lead_form", "actionId": "submit",
                                         "values": {"name": "Someone", "email": email, "phone": "000"}, "displayText": "sent"})


def test_runs_with_production_flags():
    defaults = get_settings().model_fields
    for flag in ("education_validate_block_actions", "education_compositions", "education_template_leadins"):
        assert getattr(education_agent.settings, flag) is defaults[flag].default is True


@pytest.mark.asyncio
async def test_typing_another_students_email_does_not_reveal_their_profile():
    agent = make_agent([[_chunk("Thanks, noted.")]] * 4)
    agent.memory.profiles[("c", "victim")] = dict(VICTIM)
    await _submit_contact(agent, "stranger", "ASHA@x.com")

    stranger = agent.memory.profiles[("c", "stranger")]
    assert not stranger.get("countries") and not stranger.get("budget") and not stranger.get("english_score")
    summary = [e["block"] for e in await _turn(agent, "stranger", "what do you know about me?")
               if e["type"] == "ui_block" and e["block"]["type"] == "profile_summary"]
    shown = " ".join(r["value"] for b in summary for r in b["data"]["rows"])
    assert "6.5" not in shown and "Australia" not in shown and "30,000" not in shown


@pytest.mark.asyncio
async def test_own_contact_details_are_still_saved_and_other_profile_untouched():
    agent = make_agent([[_chunk("Thanks, noted.")]] * 4)
    agent.memory.profiles[("c", "victim")] = dict(VICTIM)
    await _submit_contact(agent, "stranger", "asha@x.com")

    assert agent.memory.profiles[("c", "stranger")]["contact"] == {"name": "Someone", "email": "asha@x.com", "phone": "000"}
    assert agent.memory.profiles[("c", "victim")] == VICTIM
