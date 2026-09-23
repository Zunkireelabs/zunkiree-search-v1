"""
One-off seed for dental-city's tenant_quick_facts rows (ZUNKIREE-FAST-FACTS-BRIEF §1.4).

Sourced from what's already ingested into dental-city's Pinecone namespace /
document_chunks (read via a DB query, not re-derived) — see the QA chunks and
the "Dental City Services" chunk. No prices were found in the ingested
content (dental-city's prices live in ClinicMD's treatments table and are
already served fast, without embeddings, by the list_services tool — nothing
to seed here for that).

ClinicMD's branches.open_time/close_time are NULL for dental-city (verified
live against the ClinicMD Supabase project on 2026-09-23), so this is not a
second copy of data ClinicMD already owns (S4-TENANT-CONFIG-BRIEF finding
#3) — it's the only copy. clinic_tools._hours_from_clinicmd_branch still
prefers ClinicMD's value over this one if that ever changes.

Idempotent: deletes and re-inserts this tenant's rows, so it's safe to re-run
after editing the FACTS list below.

Usage (from backend/):
    .venv311/bin/python -m scripts.seed_dental_city_quick_facts
"""
import asyncio

from sqlalchemy import delete, select

from app.database import async_session_maker
from app.models.customer import Customer
from app.models.tenant_quick_fact import TenantQuickFact

SITE_ID = "dental-city"

FACTS = [
    {
        "category": "hours",
        "keywords": ["hour", "hours", "open", "opening", "close", "closing", "timing", "time are you"],
        "answer": "Dental City is open every day, 10:00 AM to 8:00 PM.",
    },
    {
        "category": "address",
        "keywords": ["located", "location", "address", "where are you", "where is"],
        "answer": "Dental City is located in Thimi, Bhaktapur, Nepal.",
    },
    {
        "category": "contact",
        "keywords": ["phone", "number", "call you", "contact"],
        "answer": "You can reach Dental City at 980-1222339.",
    },
    {
        "category": "contact",
        "keywords": ["email"],
        "answer": "You can email Dental City at thedentalcity@gmail.com.",
    },
    {
        "category": "staff",
        "keywords": ["dentist", "doctor", "who is the", "lead dentist"],
        "answer": "Dr. Bidhan Shrestha is the lead dentist at Dental City.",
    },
    {
        "category": "services_overview",
        "keywords": ["what services", "what do you offer", "what treatments", "services do you", "what kind of"],
        "answer": (
            "Dental City, led by Dr. Bidhan Shrestha, offers General Dentistry (preventive care like "
            "exams and cleanings), Cosmetic Dentistry, Restorative Dentistry (repairing damaged or "
            "missing teeth), and Oral Surgery. Ask about a specific treatment for its price and duration."
        ),
    },
]


async def main() -> None:
    async with async_session_maker() as db:
        result = await db.execute(select(Customer).where(Customer.site_id == SITE_ID))
        customer = result.scalar_one_or_none()
        if not customer:
            raise SystemExit(f"No customer found with site_id={SITE_ID!r}")

        await db.execute(delete(TenantQuickFact).where(TenantQuickFact.customer_id == customer.id))
        for fact in FACTS:
            db.add(TenantQuickFact(customer_id=customer.id, **fact))
        await db.commit()
        print(f"Seeded {len(FACTS)} quick facts for {SITE_ID} (customer_id={customer.id}).")


if __name__ == "__main__":
    asyncio.run(main())
