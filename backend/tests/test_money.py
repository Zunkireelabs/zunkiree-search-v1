"""Money: amount + ISO currency, one display rule, no conversion. The widget has its own copy of the formatter; its test
vectors are run through the Python one here so the two cannot drift apart."""
import re
from pathlib import Path

import pytest

from app.services.education_catalog import Catalog, CountryRecord
from app.services.education_followup import catalog_currency_code, extract_slots
from app.services.education_profile import display_value, profile_rows
from app.services.education_tools import execute_education_tool
from app.services.money import Money, format_money, format_money_range, normalize_currency
from tests.test_education_consistency import make_catalog

WIDGET_MONEY = Path(__file__).resolve().parents[2] / "widget" / "src" / "components" / "blocks" / "money.ts"


# ---- the formatter, including the widget's own vectors ----

def _widget_vectors() -> list[tuple[float, str, str]]:
    src = WIDGET_MONEY.read_text()
    body = src[src.index("export const MONEY_VECTORS"):]
    return [(float(a), c, e) for a, c, e in re.findall(r"\[(-?[\d.]+), '([^']*)', '([^']*)'\]", body)]


def test_the_widget_vectors_were_found():
    assert len(_widget_vectors()) >= 15


@pytest.mark.parametrize("amount,currency,expected", _widget_vectors())
def test_python_formats_every_widget_vector_identically(amount, currency, expected):
    assert format_money(amount, currency) == expected


def test_widget_alias_table_matches_python():
    src = WIDGET_MONEY.read_text()
    block = src[src.index("const ALIASES"):src.index("const SYMBOLS")]
    from app.services.money import CURRENCY_ALIASES
    widget = {k.strip("'"): v for k, v in re.findall(r"('[^']+'|\w+): '([A-Z]{3})'", block)}
    assert widget == CURRENCY_ALIASES


@pytest.mark.parametrize("amount,currency,expected", [
    (2_500_000, "NPR", "NPR 25,00,000"),
    (200_000, "NPR", "NPR 2,00,000"),
    (99_999, "INR", "INR 99,999"),
    (10_000_000, "INR", "INR 1,00,00,000"),
    (1_000_000, "USD", "$1,000,000"),       # western grouping outside NPR/INR
    (1_000_000, "GBP", "£1,000,000"),
    (1_000_000, "AUD", "AUD 1,000,000"),
])
def test_grouping_follows_the_currency(amount, currency, expected):
    assert format_money(amount, currency) == expected


def test_lakh_is_never_part_of_the_data_or_the_default_display():
    assert "lakh" not in format_money(2_500_000, "NPR").lower()


@pytest.mark.parametrize("raw,code", [("$", "USD"), ("usd", "USD"), ("US$", "USD"), ("£", "GBP"), ("€", "EUR"),
                                      ("NPR", "NPR"), ("npr", "NPR"), ("Nrs", "NPR"), ("₹", "INR"), ("a$", "AUD"),
                                      ("chf", "CHF"), ("Zorb", "Zorb"), ("", "")])
def test_currency_normalisation(raw, code):
    assert normalize_currency(raw) == code


def test_ranges_do_not_repeat_a_currency_code():
    assert format_money_range(14000, 28000, "USD") == "$14,000–$28,000"
    assert format_money_range(14000, 28000, "NPR") == "NPR 14,000–28,000"
    assert format_money_range(9000, 9000, "NPR") == "NPR 9,000"


# ---- Money: no conversion, ever ----

def test_money_normalises_its_currency_and_formats():
    m = Money(2_500_000, "npr")
    assert m.currency == "NPR" and m.format() == "NPR 25,00,000"


def test_same_currency_amounts_compare():
    assert Money(5, "$").compare(Money(6, "usd")) == -1
    assert Money(6, "USD").compare(Money(6, "$")) == 0
    assert Money(7, "USD").compare(Money(6, "USD")) == 1


def test_different_currencies_are_not_comparable_because_there_is_no_exchange_rate():
    assert Money(2_000_000, "NPR").compare(Money(20_000, "GBP")) is None


# ---- catalog ----

def test_a_legacy_symbol_catalog_is_normalised_to_an_iso_code():
    assert Catalog(site_id="x", currency="$").currency == "USD"
    assert Catalog(site_id="x", currency="npr").currency == "NPR"
    assert Catalog(site_id="x").currency == "USD"


def test_the_sample_catalog_file_still_loads_with_its_dollar_sign():
    from app.services.education_catalog import CATALOG_DIR, load_catalog_file
    assert load_catalog_file(CATALOG_DIR / "admizz-test.json").currency == "USD"


def test_the_follow_up_parser_and_the_catalog_agree_on_codes():
    assert catalog_currency_code("$") == "USD" and catalog_currency_code("NPR") == "NPR"


# ---- what students see, in an NPR catalog ----

def _npr_catalog() -> Catalog:
    return Catalog(site_id="npr-test", currency="NPR", countries=[
        CountryRecord(id="uk", label="U.K.", tuition_min=1_500_000, tuition_max=2_500_000, living_min=1_000_000,
                      living_max=1_400_000, ielts_min=6.5, intakes=["September"])])


def test_cost_calculator_speaks_npr():
    block = execute_education_tool("show_cost_calculator", {"country": "uk"}, {}, _npr_catalog()).block
    assert block.data["currency"] == "NPR"
    assert "NPR 15,00,000–25,00,000" in block.fallback_text


def test_budget_slider_unit_is_the_iso_code():
    assert execute_education_tool("show_budget_slider", {}, {}, _npr_catalog()).block.data["unit"] == "NPR"


def test_country_facts_and_comparison_use_the_same_formatter():
    cat = _npr_catalog()
    facts = execute_education_tool("show_country_facts", {"country": "uk"}, {}, cat).block
    assert {r["label"]: r["value"] for r in facts.data["rows"]}["Tuition / year"] == "NPR 15,00,000–25,00,000"


def test_profile_budget_is_written_in_the_catalog_currency():
    assert display_value("budget", 2_500_000, "NPR") == "NPR 25,00,000 / year"
    assert display_value("budget", 40_000, "$") == "$40,000 / year"
    assert profile_rows({"budget": 2_500_000}, {}, "NPR") == [{"label": "Budget", "value": "NPR 25,00,000 / year"}]


def test_match_reasons_mention_the_budget_in_npr():
    profile = {"budget": 5_000_000}
    items = execute_education_tool("show_country_matches", {}, profile, _npr_catalog()).block.data["items"]
    assert any("NPR 50,00,000" in r["text"] for r in items[0]["reasons"])


def test_usd_output_is_unchanged_from_before():
    block = execute_education_tool("show_country_facts", {"country": "uk"}, {}, make_catalog()).block
    assert {r["label"]: r["value"] for r in block.data["rows"]}["Tuition / year"] == "$15,000–$25,000"


def test_lakh_in_a_students_message_is_applied_only_to_an_npr_catalog():
    assert extract_slots("under 20 lakh", _npr_catalog()) == {"budget": 2_000_000}
    assert extract_slots("under 20 lakh", make_catalog()) == {}
