"""Readable text of an Admizz website page, for the knowledge base.

The shared extractor (app.utils.crawling.extract_text_from_html) deletes every element whose class or id merely CONTAINS "ad",
"nav", "menu", "header", "footer"...; Tailwind's `leading-relaxed` contains "ad", so on this site it removes the paragraphs and
keeps footer boilerplate. It is used by every tenant's ingestion, so it stays as it is; this module is explicit and opt-in, for
the Admizz website only.

It reads the page the way the page is built: text grouped under its headings (a FAQ question stays with its answer, and every
block starts with its heading path so a chunk always says what it is about), the sources and "checked" statement kept, and the
related articles, calls to action, statistic panels and marketing sections left out. Outbound source links are collected
separately (for provenance in the manifest) and are NOT put into the text the AI reads.

Nothing here verifies a page: extraction only decides which words are the page's own content.
"""
import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

_REMOVE = ["script", "style", "noscript", "iframe", "svg", "form", "nav", "header", "footer", "aside", "template"]
_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4}
_INLINE = {"a", "strong", "em", "b", "i", "u", "small", "code", "sup", "sub", "label", "abbr", "time", "mark", "span"}
_LEAF = {"p", "li", "td", "th", "dt", "dd", "blockquote", "summary", "figcaption"}
_BLOCK = {"p", "li", "ul", "ol", "div", "section", "article", "table", "tr", "td", "th", "dl", "dt", "dd", "blockquote",
          "h1", "h2", "h3", "h4", "h5", "h6"}

# A section that starts with one of these headings is not the page's own content: it is dropped together with its sub-headings.
_DROP_HEADING = re.compile(
    r"^(related (articles|guides|reading|posts)|more articles|study abroad insights|ready to build|take the first step|our alumni|"
    r"students who made it|our students made it|our success stories|testimonials?|what (our )?students say|"
    r"(book|schedule) a (free )?(counsel|consult|demo)|get in touch|contact us|follow us|share this|about (the )?author|about admizz)",
    re.IGNORECASE)
# Single lines that are only a button, label or call to action.
_BOILERPLATE = {"learn more", "read more", "book a free counseling session", "book a free demo class", "schedule a free consultation",
                "register now", "apply now", "accepting applications", "email us", "get started", "view all", "contact us",
                "24hr response", "average reply time", "free consultation", "no commitment"}
_SOCIAL = ("facebook.com", "twitter.com", "x.com", "instagram.com", "youtube.com", "youtu.be", "tiktok.com", "linkedin.com",
           "forms.gle", "wa.me", "whatsapp.com", "admizz.com", "admizzeducation.com")

_PANEL_MAX_CHARS = 400      # a heading-less panel this small whose lines are all short is a statistics / label panel
_PANEL_AVG_LINE = 25
_THIN = 300
_MAX_REFERENCES = 20
_MAX_FAQ = 40
_DEDUP_MIN_CHARS = 30       # a repeated body shorter than this ('Yes.') is an ordinary short answer, not a repeated section
_LIST_LINES = 8
_LIST_LINE_MAX = 60
_LIST_HEADING = re.compile(r"universit|college|institution|partner", re.IGNORECASE)
_MAX_ANSWER = 2000


@dataclass
class ExtractedPage:
    title: str = ""
    text: str = ""
    blocks: list = field(default_factory=list)       # the text, one entry per block: "heading path\nline\nline"
    warnings: list = field(default_factory=list)
    references: list = field(default_factory=list)   # [{"text", "url"}]: outbound https links, for provenance only
    dropped: list = field(default_factory=list)      # headings of the sections that were left out


def _norm(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return re.sub(r"\(\s+", "(", re.sub(r"\s+([.,;:!?)])", r"\1", text))


def _has_block(tag: Tag) -> bool:
    return tag.find(_BLOCK) is not None


def _tokens(root: Tag) -> list[tuple]:
    """The page in reading order: ("h", level, text) for a heading, ("t", text) for a line of text."""
    out: list[tuple] = []

    def emit(parts: list[str]) -> None:
        text = _norm(" ".join(parts))
        if text:
            out.append(("t", text))

    def walk(element: Tag) -> None:
        run: list[str] = []
        for child in element.children:
            if isinstance(child, Comment):
                continue
            if isinstance(child, NavigableString):
                if str(child).strip():
                    run.append(str(child))
                continue
            if not isinstance(child, Tag):
                continue
            name = child.name
            if name in _HEADINGS:
                emit(run), run.clear()
                if heading := _norm(child.get_text(" ", strip=True)):
                    out.append(("h", _HEADINGS[name], heading))
            elif name == "br":
                emit(run), run.clear()
            elif name in _INLINE and not _has_block(child):
                run.append(child.get_text(" ", strip=True))
            elif name in _LEAF and not _has_block(child):
                emit(run), run.clear()
                emit([child.get_text(" ", strip=True)])
            else:
                emit(run), run.clear()
                walk(child)
        emit(run)

    walk(root)
    return out


def _is_panel(element: Tag) -> bool:
    """A statistics / label strip: no heading, little text, only short lines ('London' 'Capital', '95%' 'Approval Rate')."""
    if element.find(list(_HEADINGS)):
        return False
    lines = [t[1] for t in _tokens(element) if t[0] == "t"]
    total = sum(len(line) for line in lines)
    return bool(lines) and total <= _PANEL_MAX_CHARS and total / len(lines) < _PANEL_AVG_LINE


def _references(root: Tag) -> list[dict]:
    found, seen = [], set()
    for a in root.find_all("a", href=True):
        parts = urlsplit(a["href"].strip())
        host = (parts.hostname or "").lower()
        if parts.scheme != "https" or not host or any(host == s or host.endswith("." + s) for s in _SOCIAL):
            continue
        url, text = a["href"].strip(), _norm(a.get_text(" ", strip=True))
        if text and url not in seen:
            seen.add(url)
            found.append({"text": text, "url": url})
    return found[:_MAX_REFERENCES]


def _json_nodes(data):
    if isinstance(data, dict):
        yield data
        for value in data.values():
            yield from _json_nodes(value)
    elif isinstance(data, list):
        for item in data:
            yield from _json_nodes(item)


def _as_text(value) -> str:
    return _norm(BeautifulSoup(str(value or ""), "html.parser").get_text(" ", strip=True))[:_MAX_ANSWER]


def _faq_pairs(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """Question/answer pairs from the page's own FAQPage structured data (some pages keep the answers only there)."""
    pairs: list[tuple[str, str]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or script.get_text() or "")
        except ValueError:
            continue
        for node in _json_nodes(data):
            types = node.get("@type")
            if "FAQPage" not in (types if isinstance(types, list) else [types]) or not isinstance(node.get("mainEntity"), list):
                continue
            for entity in node["mainEntity"]:
                if not isinstance(entity, dict) or not isinstance(entity.get("acceptedAnswer"), dict):
                    continue
                question, answer = _as_text(entity.get("name")), _as_text(entity["acceptedAnswer"].get("text"))
                if question and answer:
                    pairs.append((question, answer))
    return pairs[:_MAX_FAQ]


def _keep_line(line: str) -> bool:
    """Not a bare step counter ("02"), a lone symbol, or a button/label line."""
    return (len(line) >= 2 and re.search(r"\w", line) is not None and not re.fullmatch(r"\d{1,3}", line)
            and line.lower().rstrip(".!") not in _BOILERPLATE)


def extract_page(html: str) -> ExtractedPage:
    soup = BeautifulSoup(html or "", "html.parser")
    page = ExtractedPage(title=_norm(soup.title.get_text(" ", strip=True)) if soup.title else "")
    faq = _faq_pairs(soup)
    for element in soup.find_all(_REMOVE):
        element.decompose()
    for button in soup.find_all("button"):              # tab, filter and call-to-action buttons; a question inside a heading stays
        if button.find_parent(list(_HEADINGS)) is None:
            button.decompose()
    main = soup.find("main")
    if main is None:
        page.warnings.append("no_main")
    root = main or soup.find("article") or soup.body or soup

    if main is not None:       # statistics strips directly under <main> (a country page's facts and numbers panels)
        for child in [c for c in root.children if isinstance(c, Tag) and c.name in ("section", "div", "article")]:
            if _is_panel(child):
                child.decompose()
    page.references = _references(root)

    tokens = _tokens(root)
    if not any(t[0] == "h" for t in tokens):
        page.warnings.append("no_headings")

    blocks: list[dict] = [{"level": 0, "path": "", "lines": [], "parent": None}]
    stack: list[tuple[int, str]] = []
    owners: list[tuple[int, int]] = []     # (level, index into blocks) of the headings that are currently open
    drop_level: int | None = None
    for token in tokens:
        if token[0] == "t":
            blocks[-1]["lines"].append(token[1])
            continue
        _, level, heading = token
        if drop_level is not None and level > drop_level:
            blocks.append({"level": level, "path": heading, "lines": [], "drop": True, "parent": None})
            continue
        drop_level = None
        if _DROP_HEADING.match(heading):
            drop_level = level
            page.dropped.append(heading)
            blocks.append({"level": level, "path": heading, "lines": [], "drop": True, "parent": None})
            continue
        while stack and stack[-1][0] >= level:
            stack.pop()
        while owners and owners[-1][0] >= level:
            owners.pop()
        if level > 1:
            stack.append((level, heading))
        path = heading if level == 1 else " › ".join(h for _, h in stack)
        blocks.append({"level": level, "path": path, "lines": [], "parent": owners[-1][1] if owners else None})
        owners.append((level, len(blocks) - 1))

    # A heading with no text and no sub-headings (a title-only card such as "Personalized Experience") is a line of its section.
    parents = {b["parent"] for b in blocks if b.get("parent") is not None}
    for index, block in enumerate(blocks):
        parent = block.get("parent")
        if block.get("drop") or block["lines"] or block["level"] < 2 or index in parents or parent is None or blocks[parent].get("drop"):
            continue
        blocks[parent]["lines"].append(block["path"].rsplit(" › ", 1)[-1])
        block["drop"] = True

    rendered: list[str] = []
    seen_bodies: set[str] = set()
    for block in blocks:
        if block.get("drop"):
            continue
        lines, previous = [], None
        for line in block["lines"]:
            if _keep_line(line) and line != previous:
                lines.append(line)
            previous = line
        if not lines and block["level"] != 1:
            continue                                  # a heading with no text of its own: its children carry it in their path
        if block["level"] == 0 and not any(len(line) >= 50 for line in lines):
            continue                                  # breadcrumb tags, taglines and similar leftovers before the first heading
        body = re.sub(r"\s+", " ", " ".join(lines)).strip().lower()
        if len(body) >= _DEDUP_MIN_CHARS and block["level"] > 0:
            if body in seen_bodies:                   # the page renders the same section twice (mobile and desktop copies)
                if "repeated_sections" not in page.warnings:
                    page.warnings.append("repeated_sections")
                continue
            seen_bodies.add(body)
        if (block["level"] > 0 and _LIST_HEADING.search(block["path"].rsplit(" › ", 1)[-1]) and len(lines) >= _LIST_LINES
                and all(len(line) < _LIST_LINE_MAX for line in lines) and "university_list" not in page.warnings):
            page.warnings.append("university_list")   # names of universities: unverified marketing, to be reviewed, not facts
        rendered.append("\n".join(([block["path"]] if block["path"] else []) + lines))

    answered = {b.split("\n")[0].rsplit(" › ", 1)[-1] for b in rendered if "\n" in b}
    for question, answer in faq:                      # answers the visible page does not carry
        if question not in answered:
            rendered.append(f"Frequently Asked Questions › {question}\n{answer}")
            answered.add(question)

    page.blocks = rendered
    page.text = "\n\n".join(rendered)
    if not page.text:
        page.warnings.append("empty")
    elif len(page.text) < _THIN:
        page.warnings.append("thin_content")
    return page
