"""One clear disposition for every page in the reviewed ingestion manifest.

  ready      technically ready for a future, separately approved ingestion
  review     a person must look at it first (a university list, an undated marketing page, an extraction problem)
  excluded   not to be ingested, with the recorded reason (for example a link-only sign-up page)
  undecided  the manifest does not hold enough information to decide; nothing is guessed

"Ready" never means verified. Every page stays `verified: false`: public website text is not promoted to catalog data here, and a
manifest that claims otherwise is refused. The order of the result is the order a future ingestion would use: source-backed pages
first, then dated pages.

Pure functions only: nothing here reads a database or the network, and the manifest file is never modified.
"""
import json
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path

READY, REVIEW, EXCLUDED, UNDECIDED = "ready", "review", "excluded", "undecided"
STALE_AFTER_DAYS = 365
_STATUS_RANK = {READY: 0, REVIEW: 1, EXCLUDED: 2, UNDECIDED: 3}
_CLASS_RANK = {"source_backed": 0, "dated": 1, "explanatory": 2}
_EXTRACTION_WARNINGS = ("no_main", "no_headings", "thin_content", "empty")


@dataclass(frozen=True)
class Disposition:
    page_id: str
    status: str
    reasons: tuple = ()      # why a page is in review, excluded or undecided
    notes: tuple = ()        # things to know about a page that does not change its status


def load_manifest(path: Path) -> dict:
    """The dry-run manifest at `path`; ValueError if the file is not one."""
    try:
        manifest = json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        raise ValueError(f"manifest unreadable: {e}") from e
    if not isinstance(manifest, dict) or manifest.get("dry_run") is not True or not isinstance(manifest.get("pages"), list) \
            or not all(isinstance(p, dict) for p in manifest["pages"]):
        raise ValueError("not a dry-run manifest: expected {dry_run: true, pages: [...]}")
    return manifest


def _age_note(freshness: dict, today: date) -> str | None:
    checked, published = freshness.get("checked"), freshness.get("published")
    stated = checked or published
    if not stated:
        return None
    try:
        when = datetime.strptime(stated, "%Y-%m-%d" if len(stated) == 10 else "%Y-%m").date()
    except ValueError:
        return None
    return "published_over_a_year_ago_check_freshness" if not checked and when < today - timedelta(days=STALE_AFTER_DAYS) else None


def decide(entry: dict, *, today: date) -> Disposition:
    page_id = str(entry.get("id") or "?")
    eligible = entry.get("eligible_for_ingestion")
    needed = ["id", "eligible_for_ingestion", "plan_action", "verified"]
    if eligible:
        needed += ["content_class", "canonical_url", "chunks", "warnings"]
    missing = [k for k in needed if k not in entry or entry[k] is None]
    if missing:
        return Disposition(page_id, UNDECIDED, tuple(f"manifest_incomplete:{k}" for k in missing))
    if entry["verified"] is not False:
        return Disposition(page_id, UNDECIDED, ("manifest_claims_verified",))
    if not eligible:
        return Disposition(page_id, EXCLUDED, (str(entry["plan_action"]).removeprefix("skip: "),))
    if entry["content_class"] not in _CLASS_RANK:
        return Disposition(page_id, UNDECIDED, (f"unknown_content_class:{entry['content_class']}",))

    warnings = entry["warnings"]
    reasons: list[str] = []
    if entry["content_class"] == "explanatory":
        reasons.append("no_date_or_official_source")
        if entry.get("kind") == "service":
            reasons.append("marketing_service_page")
    if "university_list" in warnings:
        reasons.append("university_names_unverified")
    reasons += [f"extraction_warning:{w}" for w in _EXTRACTION_WARNINGS if w in warnings]

    notes: list[str] = []
    if "repeated_sections" in warnings:
        notes.append("repeated_sections_removed")
    if (age := _age_note(entry.get("registry_freshness") or {}, today)):
        notes.append(age)
    overlap = entry.get("overlap") or {}
    if overlap.get("match") == "title":
        notes.append("title_overlap_with_existing_job_not_proof_of_same_source")
    elif overlap.get("match") == "url":
        notes.append("same_url_job_exists")
    return Disposition(page_id, REVIEW if reasons else READY, tuple(reasons), tuple(notes))


def dispositions_for(manifest: dict, *, today: date) -> list[Disposition]:
    """Every page's disposition, in ingestion order: ready first (source-backed, then dated), then review, excluded, undecided."""
    pages = manifest["pages"]
    ranked = []
    for index, entry in enumerate(pages):
        d = decide(entry, today=today)
        ranked.append((_STATUS_RANK[d.status], _CLASS_RANK.get(entry.get("content_class"), 3), index, d))
    return [d for *_, d in sorted(ranked, key=lambda r: r[:3])]


def apply_review_overrides(dispositions: list[Disposition], overrides: dict) -> tuple[list[Disposition], list[str]]:
    """A reviewer may turn a `review` page into `ready`, naming themselves and giving a reason. Nothing else can be overridden."""
    by_id = {d.page_id: d for d in dispositions}
    problems: list[str] = []
    approved: dict[str, Disposition] = {}
    for page_id, override in (overrides or {}).items():
        current = by_id.get(page_id)
        if current is None:
            problems.append(f"{page_id}: not a page in the manifest")
        elif current.status != REVIEW:
            problems.append(f"{page_id}: only a page in review can be overridden (it is {current.status})")
        elif not isinstance(override, dict) or override.get("status") != READY:
            problems.append(f"{page_id}: an override can only set status to 'ready'")
        elif not str(override.get("reviewed_by") or "").strip() or not str(override.get("reason") or "").strip():
            problems.append(f"{page_id}: an override needs reviewed_by and a reason")
        else:
            note = f"approved_after_review by {override['reviewed_by'].strip()}: {override['reason'].strip()}"
            approved[page_id] = replace(current, status=READY, notes=current.notes + (note,))
    return [approved.get(d.page_id, d) for d in dispositions], problems


def summary(dispositions: list[Disposition]) -> dict:
    return {status: sum(1 for d in dispositions if d.status == status) for status in (READY, REVIEW, EXCLUDED, UNDECIDED)}
