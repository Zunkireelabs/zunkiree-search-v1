"""
Money: an amount plus the currency it is in, and one way to display it.

Amounts are stored as whole numbers in a stated currency (ISO code). How they are written for a student is purely a
display rule: NPR/INR use Indian digit grouping ("NPR 25,00,000"), USD/GBP/EUR use their symbol ("£20,000"), and any
other currency uses its code ("AUD 20,000"). "lakh" is never part of the data.

There is deliberately NO currency conversion: two amounts in different currencies are not comparable here (`compare`
returns None), so a caller treats that as "unknown" instead of guessing an exchange rate.

The widget has the same formatter (widget/src/components/blocks/money.ts); a backend test runs the widget's own test
vectors through this one so the two cannot drift apart.
"""
import re
from dataclasses import dataclass

# Text students, catalogs and old data use for a currency -> ISO code. Lower-cased keys.
CURRENCY_ALIASES = {
    "$": "USD", "usd": "USD", "us$": "USD", "£": "GBP", "gbp": "GBP", "€": "EUR", "eur": "EUR",
    "a$": "AUD", "aud": "AUD", "c$": "CAD", "cad": "CAD",
    "npr": "NPR", "nrs": "NPR", "nr": "NPR", "₹": "INR", "inr": "INR",
}

_SYMBOLS = {"USD": "$", "GBP": "£", "EUR": "€"}
_INDIAN_GROUPING = {"NPR", "INR"}


def normalize_currency(value: str) -> str:
    """ISO code for a code or symbol ('$' -> 'USD', 'npr' -> 'NPR'). Anything unrecognised is returned trimmed, upper-cased
    if it looks like a code, so an unknown currency still displays rather than failing."""
    token = (value or "").strip()
    known = CURRENCY_ALIASES.get(token.lower())
    if known:
        return known
    return token.upper() if re.fullmatch(r"[A-Za-z]{3}", token) else token


def _group(n: int, indian: bool) -> str:
    digits = str(abs(n))
    if indian and len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        head = re.sub(r"(\d)(?=(\d{2})+$)", r"\1,", head)
        grouped = f"{head},{tail}"
    else:
        grouped = f"{abs(n):,}"
    return f"-{grouped}" if n < 0 else grouped


def format_money(amount: float, currency: str) -> str:
    """'NPR 25,00,000', '£20,000', 'AUD 20,000'. Whole units only."""
    code = normalize_currency(currency)
    grouped = _group(int(round(amount)), code in _INDIAN_GROUPING)
    symbol = _SYMBOLS.get(code)
    if symbol:
        return f"{symbol}{grouped}"
    return f"{code} {grouped}" if code else grouped


def format_money_range(low: float, high: float, currency: str) -> str:
    """'$14,000–$28,000' for symbol currencies, 'NPR 14,000–28,000' for code currencies (the code is not repeated)."""
    code = normalize_currency(currency)
    if low == high:
        return format_money(low, code)
    if code in _SYMBOLS:
        return f"{format_money(low, code)}–{format_money(high, code)}"
    return f"{format_money(low, code)}–{_group(int(round(high)), code in _INDIAN_GROUPING)}"


@dataclass(frozen=True)
class Money:
    amount: int
    currency: str

    def __post_init__(self):
        object.__setattr__(self, "currency", normalize_currency(self.currency))

    def format(self) -> str:
        return format_money(self.amount, self.currency)

    def compare(self, other: "Money") -> int | None:
        """-1, 0 or 1; None when the currencies differ (there is no exchange rate, so they cannot be compared)."""
        if self.currency != other.currency:
            return None
        return (self.amount > other.amount) - (self.amount < other.amount)
