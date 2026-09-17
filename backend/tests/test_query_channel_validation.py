"""
ZUNKIREE-CLEANUP-BRIEF C3: `channel` had no enum validation, so "Voice", "VOICE"
or any typo silently degraded a voice caller to chat-length replies instead of
erroring. `QueryRequest.channel` now carries a `^(chat|voice)$` pattern, which
FastAPI/Pydantic turns into a 422 on any other value at the request boundary.
"""
import pytest
from pydantic import ValidationError

from app.api.query import QueryRequest


def test_invalid_channel_value_is_rejected():
    for bad in ("Voice", "VOICE", "voise", "phone"):
        with pytest.raises(ValidationError):
            QueryRequest(site_id="dental-city", question="hi", channel=bad)


def test_omitted_channel_still_defaults_to_none():
    req = QueryRequest(site_id="dental-city", question="hi")
    assert req.channel is None


@pytest.mark.parametrize("channel", ["chat", "voice"])
def test_valid_channel_values_pass(channel):
    req = QueryRequest(site_id="dental-city", question="hi", channel=channel)
    assert req.channel == channel
