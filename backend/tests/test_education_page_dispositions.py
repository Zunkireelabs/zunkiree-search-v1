"""Every eligible page gets one clear disposition from the reviewed manifest: ready, review (a person must look at it) or excluded
(with the reason). 'Ready' means technically ready; it never means verified, and every page stays verified=false. A page the manifest
cannot decide is 'undecided', never guessed."""
import json
from datetime import date

import pytest

from app.services.education_page_dispositions import (
    EXCLUDED, READY, REVIEW, UNDECIDED, Disposition, apply_review_overrides, decide, dispositions_for, load_manifest, summary,
)
from app.services.education_sources import SOURCES_DIR

TODAY = date(2026, 10, 13)
SNAPSHOT = SOURCES_DIR / "admizz-test.manifest.json"


def _entry(**kw):
    base = dict(id="p", eligible=True, eligible_for_ingestion=True, plan_action="add", canonical_url="https://admizzeducation.com/p",
                content_class="dated", chunks=3, warnings=[], verified=False, kind="article", category="visa",
                registry_freshness={"sitemap_lastmod": "2026-10-08", "published": "2026-10-05", "checked": None, "ingested_at": None},
                overlap=None)
    return {**base, **kw}


# --- the rules --------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("content_class", ["source_backed", "dated"])
def test_a_dated_or_source_backed_page_with_no_flags_is_ready(content_class):
    d = decide(_entry(content_class=content_class), today=TODAY)
    assert d.status == READY and d.reasons == ()


def test_an_explanatory_page_needs_individual_review():
    d = decide(_entry(content_class="explanatory"), today=TODAY)
    assert d.status == REVIEW and "no_date_or_official_source" in d.reasons


def test_a_marketing_service_page_is_called_out_as_such():
    d = decide(_entry(content_class="explanatory", kind="service"), today=TODAY)
    assert d.status == REVIEW and "marketing_service_page" in d.reasons


def test_a_page_with_a_university_list_needs_review_even_if_it_is_dated():
    d = decide(_entry(warnings=["university_list"]), today=TODAY)
    assert d.status == REVIEW and "university_names_unverified" in d.reasons


@pytest.mark.parametrize("warning", ["no_main", "no_headings", "thin_content", "empty"])
def test_an_extraction_warning_needs_review(warning):
    d = decide(_entry(warnings=[warning]), today=TODAY)
    assert d.status == REVIEW and f"extraction_warning:{warning}" in d.reasons


def test_repeated_sections_alone_is_only_a_note_because_the_repeats_were_already_removed():
    d = decide(_entry(warnings=["repeated_sections"]), today=TODAY)
    assert d.status == READY and "repeated_sections_removed" in d.notes


def test_a_page_the_pipeline_excluded_stays_excluded_with_its_reason():
    d = decide(_entry(eligible_for_ingestion=False, plan_action="skip: link_only_category"), today=TODAY)
    assert d.status == EXCLUDED and d.reasons == ("link_only_category",)
    assert decide(_entry(eligible=False, eligible_for_ingestion=False, plan_action="skip: content_type"), today=TODAY).reasons == ("content_type",)


@pytest.mark.parametrize("missing", ["content_class", "canonical_url", "chunks", "warnings", "eligible_for_ingestion", "plan_action", "verified"])
def test_a_manifest_entry_without_enough_information_is_undecided_not_guessed(missing):
    entry = _entry()
    del entry[missing]
    d = decide(entry, today=TODAY)
    assert d.status == UNDECIDED and any(missing in r for r in d.reasons)


def test_a_manifest_that_claims_a_page_is_verified_is_undecided():
    d = decide(_entry(verified=True), today=TODAY)
    assert d.status == UNDECIDED and "manifest_claims_verified" in d.reasons


def test_an_old_publication_date_adds_a_freshness_note_but_does_not_block():
    old = decide(_entry(registry_freshness={"published": "2025-07-18", "checked": None, "sitemap_lastmod": "2026-10-06", "ingested_at": None}), today=TODAY)
    assert old.status == READY and "published_over_a_year_ago_check_freshness" in old.notes
    recent = decide(_entry(), today=TODAY)
    assert recent.notes == ()


def test_a_checked_date_takes_precedence_over_an_old_publication_date():
    d = decide(_entry(registry_freshness={"published": "2025-01-01", "checked": "2026-10", "sitemap_lastmod": None, "ingested_at": None}), today=TODAY)
    assert "published_over_a_year_ago_check_freshness" not in d.notes


def test_a_title_overlap_with_an_old_job_is_noted_never_acted_on():
    d = decide(_entry(overlap={"match": "title", "job_id": "j1", "proof": "title_only_not_proven_same_source"}), today=TODAY)
    assert d.status == READY and "title_overlap_with_existing_job_not_proof_of_same_source" in d.notes


def test_an_existing_job_with_the_same_url_is_a_note_for_the_idempotency_check_not_a_decision():
    d = decide(_entry(overlap={"match": "url", "job_id": "j1", "proof": "same_url"}), today=TODAY)
    assert "same_url_job_exists" in d.notes


# --- human review overrides -----------------------------------------------------------------------------------------------------

def _two():
    return [Disposition("a", REVIEW, ("university_names_unverified",), ()), Disposition("b", EXCLUDED, ("link_only_category",), ())]


def test_a_reviewed_page_can_be_made_ready_with_a_named_reviewer_and_a_reason():
    out, problems = apply_review_overrides(_two(), {"a": {"status": "ready", "reviewed_by": "Priya", "reason": "University list removed from the guide"}})
    assert [d.status for d in out] == [READY, EXCLUDED] and problems == []
    assert any("approved_after_review" in n and "Priya" in n for n in out[0].notes)


@pytest.mark.parametrize("override", [
    {"status": "ready"}, {"status": "ready", "reviewed_by": "", "reason": "x"}, {"status": "ready", "reviewed_by": "P", "reason": " "},
    {"status": "verified", "reviewed_by": "P", "reason": "x"}, "ready", None,
])
def test_an_override_without_a_reviewer_and_reason_is_ignored_and_reported(override):
    out, problems = apply_review_overrides(_two(), {"a": override})
    assert out[0].status == REVIEW and problems


def test_only_a_review_page_can_be_overridden():
    out, problems = apply_review_overrides(_two(), {"b": {"status": "ready", "reviewed_by": "P", "reason": "x"}, "zzz": {"status": "ready", "reviewed_by": "P", "reason": "x"}})
    assert out[1].status == EXCLUDED and len(problems) == 2


# --- the real manifest ------------------------------------------------------------------------------------------------------------

def test_the_manifest_snapshot_is_the_36_page_manifest_with_35_eligible_pages():
    manifest = load_manifest(SNAPSHOT)
    assert len(manifest["pages"]) == 36 and sum(1 for p in manifest["pages"] if p["eligible_for_ingestion"]) == 35
    assert all(p["verified"] is False for p in manifest["pages"])


def test_the_disposition_of_every_page_in_the_manifest():
    ds = dispositions_for(load_manifest(SNAPSHOT), today=TODAY)
    by = {d.page_id: d for d in ds}
    assert summary(ds) == {"ready": 27, "review": 8, "excluded": 1, "undecided": 0}
    assert {i for i, d in by.items() if d.status == REVIEW} == {"uk-guide", "us-guide", "au-guide", "ca-guide", "de-guide",
                                                                "test-prep", "scholarship-assistance", "visa-assistance"}
    assert {i for i, d in by.items() if d.status == EXCLUDED} == {"book-counseling"} and by["book-counseling"].reasons == ("link_only_category",)
    assert "university_names_unverified" in by["uk-guide"].reasons and "marketing_service_page" in by["visa-assistance"].reasons


def test_dated_and_source_backed_pages_come_first_and_every_ready_page_is_one_of_them():
    manifest = load_manifest(SNAPSHOT)
    classes = {p["id"]: p["content_class"] for p in manifest["pages"]}
    ds = dispositions_for(manifest, today=TODAY)
    assert all(classes[d.page_id] in ("source_backed", "dated") for d in ds if d.status == READY)
    order = [d.page_id for d in ds if d.status == READY]
    first_source_backed = [i for i in order if classes[i] == "source_backed"]
    assert order[:len(first_source_backed)] == first_source_backed        # source-backed pages are listed (and so ingested) first


def test_the_pages_that_are_old_get_a_freshness_note():
    manifest = load_manifest(SNAPSHOT)
    cutoff = "2025-10-13"
    expected = {p["id"] for p in manifest["pages"] if p["eligible_for_ingestion"] and not p["registry_freshness"]["checked"]
                and p["registry_freshness"]["published"] and p["registry_freshness"]["published"] < cutoff}
    noted = {d.page_id for d in dispositions_for(manifest, today=TODAY) if "published_over_a_year_ago_check_freshness" in d.notes}
    assert noted == expected and expected             # not empty: some pages really are old


def test_a_manifest_file_that_is_not_a_manifest_is_refused(tmp_path):
    for content in ("not json", "[]", json.dumps({"pages": "x"}), json.dumps({"dry_run": False, "pages": []})):
        path = tmp_path / "m.json"
        path.write_text(content)
        with pytest.raises(ValueError):
            load_manifest(path)


def test_loading_and_deciding_never_modifies_the_manifest_file():
    before = SNAPSHOT.read_bytes()
    dispositions_for(load_manifest(SNAPSHOT), today=TODAY)
    assert SNAPSHOT.read_bytes() == before
