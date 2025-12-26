import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


async def crawl_url(url: str, timeout: int = 30) -> dict:
    """
    Crawl a URL and extract content.

    Args:
        url: URL to crawl
        timeout: Request timeout in seconds

    Returns:
        Dict with 'title', 'content', 'url', and 'links'
    """
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout,
    ) as client:
        response = await client.get(url)
        response.raise_for_status()

        html = response.text
        title, content = extract_text_from_html(html)
        links = extract_links(html, url)

        return {
            "title": title or url,
            "content": content,
            "url": url,
            "links": links,
        }


def extract_text_from_html(html: str) -> tuple[str, str]:
    """
    Extract title and clean text content from HTML.

    Args:
        html: Raw HTML string

    Returns:
        Tuple of (title, content)
    """
    soup = BeautifulSoup(html, "html.parser")

    # Extract title
    title = ""
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)

    # Remove unwanted elements
    for element in soup.find_all([
        "script", "style", "nav", "header", "footer",
        "aside", "form", "iframe", "noscript",
    ]):
        element.decompose()

    # Remove elements with common non-content classes/ids
    for selector in [
        "[class*='nav']", "[class*='menu']", "[class*='sidebar']",
        "[class*='footer']", "[class*='header']", "[class*='cookie']",
        "[class*='popup']", "[class*='modal']", "[class*='ad']",
        "[id*='nav']", "[id*='menu']", "[id*='sidebar']",
        "[id*='footer']", "[id*='header']",
    ]:
        for element in soup.select(selector):
            element.decompose()

    # Get main content
    main_content = soup.find("main") or soup.find("article") or soup.find("body")

    if main_content:
        # Get text with proper spacing
        text = main_content.get_text(separator="\n", strip=True)
    else:
        text = soup.get_text(separator="\n", strip=True)

    # Clean up text
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if line and len(line) > 2:  # Skip very short lines
            cleaned_lines.append(line)

    content = "\n\n".join(cleaned_lines)

    return title, content


def extract_links(html: str, base_url: str) -> list[str]:
    """
    Extract internal links from HTML.

    Args:
        html: Raw HTML string
        base_url: Base URL for resolving relative links

    Returns:
        List of absolute URLs
    """
    soup = BeautifulSoup(html, "html.parser")
    base_domain = urlparse(base_url).netloc

    links = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]

        # Skip anchors, javascript, mailto, etc.
        if href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        # Resolve relative URLs
        absolute_url = urljoin(base_url, href)

        # Only include same-domain links
        if urlparse(absolute_url).netloc == base_domain:
            # Remove fragments
            absolute_url = absolute_url.split("#")[0]
            if absolute_url not in links:
                links.append(absolute_url)

    return links


async def extract_text_from_pdf(pdf_content: bytes) -> str:
    """
    Extract text from PDF content.

    Args:
        pdf_content: PDF file bytes

    Returns:
        Extracted text
    """
    import pdfplumber
    import io

    text_parts = []

    with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

    return "\n\n".join(text_parts)
