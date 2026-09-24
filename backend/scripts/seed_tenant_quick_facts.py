"""
Generic tenant_quick_facts writer (ZUNKIREE-FAST-FACTS-BRIEF §1.4,
ZUNKIREE-FAST-FACTS-NEPALI-BRIEF §1). Replaces the dental-city-only
seed_dental_city_quick_facts.py so onboarding a new clinic (e.g. Healthy
Smile, per P3-WIDGET-THROUGH-ORCA-BRIEF §7) means writing a JSON file, not
code.

Takes a site_id and a JSON file of facts, same shape as
seed_data/dental_city_quick_facts.json (dental-city's own facts, ported
as-is from the old script's FACTS list — content unchanged):

    [
      {
        "category": "hours",          // hours | address | contact | staff |
                                       // services_overview | policy | other
        "keywords": ["hour", "hours", "खुल्ने", ...],
        "answer": "Dental City is open every day, 10:00 AM to 8:00 PM."
      },
      ...
    ]

Idempotent: deletes and re-inserts this tenant's rows, so it's safe to
re-run after editing the JSON file.

Usage (from backend/):
    .venv311/bin/python -m scripts.seed_tenant_quick_facts <site_id> <path/to/facts.json>

Example:
    .venv311/bin/python -m scripts.seed_tenant_quick_facts \\
        dental-city scripts/seed_data/dental_city_quick_facts.json
"""
import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import delete, select

from app.database import async_session_maker
from app.models.customer import Customer
from app.models.tenant_quick_fact import TenantQuickFact

VALID_CATEGORIES = {"hours", "address", "contact", "staff", "services_overview", "policy", "other"}


def _load_facts(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        raise SystemExit(f"No such file: {path}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"Invalid JSON in {path}: {e}")

    if not isinstance(data, list) or not data:
        raise SystemExit(f"{path} must contain a non-empty JSON array of facts")

    for i, fact in enumerate(data):
        missing = {"category", "keywords", "answer"} - fact.keys()
        if missing:
            raise SystemExit(f"{path}[{i}] is missing required field(s): {sorted(missing)}")
        if fact["category"] not in VALID_CATEGORIES:
            raise SystemExit(
                f"{path}[{i}] has category={fact['category']!r}, "
                f"must be one of {sorted(VALID_CATEGORIES)}"
            )
        if not isinstance(fact["keywords"], list) or not all(isinstance(k, str) for k in fact["keywords"]):
            raise SystemExit(f"{path}[{i}] keywords must be a list of strings")
        if not isinstance(fact["answer"], str) or not fact["answer"].strip():
            raise SystemExit(f"{path}[{i}] answer must be a non-empty string")

    return data


async def seed(site_id: str, facts: list[dict]) -> int:
    async with async_session_maker() as db:
        result = await db.execute(select(Customer).where(Customer.site_id == site_id))
        customer = result.scalar_one_or_none()
        if not customer:
            raise SystemExit(f"No customer found with site_id={site_id!r}")

        await db.execute(delete(TenantQuickFact).where(TenantQuickFact.customer_id == customer.id))
        for fact in facts:
            db.add(TenantQuickFact(
                customer_id=customer.id,
                category=fact["category"],
                keywords=fact["keywords"],
                answer=fact["answer"],
            ))
        await db.commit()
        return len(facts)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("site_id", help="Tenant's site_id, e.g. dental-city")
    parser.add_argument("facts_file", help="Path to a JSON file of facts (see module docstring for shape)")
    args = parser.parse_args()

    facts = _load_facts(Path(args.facts_file))
    count = await seed(args.site_id, facts)
    print(f"Seeded {count} quick facts for {args.site_id}.")


if __name__ == "__main__":
    asyncio.run(main())
