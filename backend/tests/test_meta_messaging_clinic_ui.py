"""
SBAL-Z2: new MetaMessagingClient renderers for the clinic agent's structured
`ui` — send_chips (independent label/payload per chip), send_service_cards,
send_booking_card — plus set_ice_breakers (item 5).
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.meta_messaging import MetaMessagingClient, _format_price_npr, book_service_payload


def _client_with_mocked_http(status_code=200, json_body=None):
    client = MetaMessagingClient.__new__(MetaMessagingClient)
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body or {"recipient_id": "r1", "message_id": "m1"}
    client._http = AsyncMock()
    client._http.post = AsyncMock(return_value=resp)
    return client, resp


@pytest.mark.asyncio
async def test_send_chips_uses_independent_label_and_payload():
    client, resp = _client_with_mocked_http()
    chips = [
        {"label": "10:00", "payload": "Book Lash Lift on 2026-10-10 at 10:00"},
        {"label": "Another day", "payload": "What other days is Lash Lift available?"},
    ]
    await client.send_chips(
        platform="instagram", page_id="page-1", access_token="tok",
        recipient_id="r1", text="Pick a time:", chips=chips,
    )
    _, kwargs = client._http.post.call_args
    sent = kwargs["json"]["message"]["quick_replies"]
    assert sent[0] == {"content_type": "text", "title": "10:00", "payload": "Book Lash Lift on 2026-10-10 at 10:00"}
    assert sent[1]["title"] == "Another day"


@pytest.mark.asyncio
async def test_send_chips_caps_at_thirteen():
    client, _ = _client_with_mocked_http()
    chips = [{"label": str(i), "payload": str(i)} for i in range(20)]
    await client.send_chips(
        platform="instagram", page_id="page-1", access_token="tok",
        recipient_id="r1", text="x", chips=chips,
    )
    _, kwargs = client._http.post.call_args
    assert len(kwargs["json"]["message"]["quick_replies"]) == 13


@pytest.mark.asyncio
async def test_send_service_cards_builds_title_subtitle_and_book_button_with_id():
    client, _ = _client_with_mocked_http()
    services = [{"id": "s1", "name": "Lash Lift", "price": 2500, "duration": 60, "image_url": None, "description": "d"}]
    await client.send_service_cards(
        platform="instagram", page_id="page-1", access_token="tok",
        recipient_id="r1", services=services,
    )
    _, kwargs = client._http.post.call_args
    element = kwargs["json"]["message"]["attachment"]["payload"]["elements"][0]
    assert element["title"] == "Lash Lift · NPR 2,500"
    assert element["subtitle"] == "60 min"
    assert "image_url" not in element  # no image data available — omitted, not sent as None

    import json as _json
    book_button = element["buttons"][0]
    assert book_button["title"] == "Book this"
    payload = _json.loads(book_button["payload"])
    assert payload == {"action": "book_service", "service_id": "s1", "name": "Lash Lift"}
    assert element["buttons"][1]["title"] == "Details"


@pytest.mark.asyncio
async def test_send_service_detail_book_button_matches_carousel_payload():
    """SBAL-Z5 F1 (brain review on #122): send_service_detail's "Book
    this" button must carry the byte-identical payload the carousel's own
    "Book this" sends — both built from the one shared
    book_service_payload, so they parse through the same booking handling."""
    client, _ = _client_with_mocked_http()
    await client.send_service_detail(
        platform="instagram", page_id="page-1", access_token="tok",
        recipient_id="r1", text="Highly Defining Dye is NPR 1200 and takes 45 minutes.",
        service_id="svc-xyz", service_name="Highly Defining Dye",
    )
    _, kwargs = client._http.post.call_args
    sent_payload = kwargs["json"]["message"]["attachment"]["payload"]
    assert sent_payload["template_type"] == "button"
    assert sent_payload["text"] == "Highly Defining Dye is NPR 1200 and takes 45 minutes."
    button = sent_payload["buttons"][0]
    assert button["title"] == "Book this"
    assert button["payload"] == book_service_payload("svc-xyz", "Highly Defining Dye")
    # no image/subtitle card — the whole point of F1 was no one-card carousel.
    assert "elements" not in sent_payload


@pytest.mark.asyncio
async def test_send_booking_card_includes_ref_and_location():
    client, _ = _client_with_mocked_http()
    booking = {"booking_number": "BK-999", "service": "Lash Lift", "when": "2026-10-10 10:00", "name": "Thamel Branch"}
    await client.send_booking_card(
        platform="instagram", page_id="page-1", access_token="tok",
        recipient_id="r1", booking=booking,
    )
    _, kwargs = client._http.post.call_args
    element = kwargs["json"]["message"]["attachment"]["payload"]["elements"][0]
    assert element["title"] == "Booked: Lash Lift"
    assert "BK-999" in element["subtitle"]
    assert "Thamel Branch" in element["subtitle"]


@pytest.mark.asyncio
async def test_set_ice_breakers_posts_to_messenger_profile_with_instagram_platform():
    client, _ = _client_with_mocked_http()
    questions = [
        {"question": "Book an appointment", "payload": "Book an appointment"},
        {"question": "Services & prices", "payload": "Services & prices"},
    ]
    await client.set_ice_breakers(page_id="page-1", access_token="tok", questions=questions)
    args, kwargs = client._http.post.call_args
    assert "messenger_profile" in args[0]
    assert kwargs["json"]["platform"] == "instagram"
    assert kwargs["json"]["ice_breakers"][0]["call_to_actions"] == questions


@pytest.mark.asyncio
async def test_set_ice_breakers_caps_at_four():
    client, _ = _client_with_mocked_http()
    questions = [{"question": str(i), "payload": str(i)} for i in range(10)]
    await client.set_ice_breakers(page_id="page-1", access_token="tok", questions=questions)
    _, kwargs = client._http.post.call_args
    assert len(kwargs["json"]["ice_breakers"][0]["call_to_actions"]) == 4


@pytest.mark.parametrize("value,expected", [
    (3499, "3,499"),
    (3499.0, "3,499"),
    (349, "349"),
    (349.0, "349"),
    (1000000, "1,000,000"),
    (None, ""),
])
def test_format_price_npr(value, expected):
    assert _format_price_npr(value) == expected
