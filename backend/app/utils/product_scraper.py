"""
Multi-layered product data extraction from HTML.
Extraction order (by reliability):
1. JSON-LD / Schema.org
2. Open Graph meta tags
3. Microdata
4. CSS selector heuristics
5. Platform-specific (Shopify, WooCommerce)
"""
import json
import re
import hashlib
import logging
from dataclasses import dataclass, field
from urllib.parse import urljoin
from bs4 import BeautifulSoup

logger = logging.getLogger("zunkiree.product_scraper")


@dataclass
class ProductData:
    name: str
    description: str = ""
    details: str = ""  # Rich product details (fabric, fit, construction, care)
    price: float | None = None
    currency: str = ""
    original_price: float | None = None
    images: list[str] = field(default_factory=list)
    url: str = ""
    sku: str = ""
    brand: str = ""
    category: str = ""
    sizes: list[str] = field(default_factory=list)
    colors: list[str] = field(default_factory=list)
    in_stock: bool = True
    tags: list[str] = field(default_factory=list)
    source_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "details": self.details,
            "price": self.price,
            "currency": self.currency,
            "original_price": self.original_price,
            "images": self.images,
            "url": self.url,
            "sku": self.sku,
            "brand": self.brand,
            "category": self.category,
            "sizes": self.sizes,
            "colors": self.colors,
            "in_stock": self.in_stock,
            "tags": self.tags,
            "source_hash": self.source_hash,
        }

    def embedding_text(self) -> str:
        """Build text representation for vector embedding."""
        parts = [self.name]
        if self.category:
            parts.append(self.category)
        if self.brand:
            parts.append(self.brand)
        if self.description:
            parts.append(self.description[:300])
        if self.details:
            parts.append(self.details[:700])
        if self.colors:
            parts.append(f"Colors: {', '.join(self.colors)}")
        if self.sizes:
            parts.append(f"Sizes: {', '.join(self.sizes)}")
        if self.tags:
            parts.append(f"Tags: {', '.join(self.tags)}")
        return ". ".join(parts)


def scrape_products(html: str, url: str) -> list[ProductData]:
    """
    Extract product data from HTML using multiple extraction layers.
    Returns list of ProductData found on the page.
    """
    products: list[ProductData] = []
    seen_names: set[str] = set()

    # Layer 1: JSON-LD / Schema.org
    products.extend(_extract_jsonld(html, url))

    # Layer 2: Open Graph meta tags (only if no JSON-LD products found)
    if not products:
        og_product = _extract_opengraph(html, url)
        if og_product:
            products.append(og_product)

    # Layer 3: Shopify embedded JSON
    if not products:
        products.extend(_extract_shopify(html, url))

    # Post-process: extract sizes/colors, gallery images, and rich details
    if products:
        soup = BeautifulSoup(html, "html.parser")
        for p in products:
            if not p.sizes:
                size_select = soup.find("select", {"id": re.compile(r"pa_size|pa_sizes", re.I)})
                if size_select:
                    p.sizes = [opt.text.strip() for opt in size_select.find_all("option") if opt.get("value")]
            if not p.colors:
                color_select = soup.find("select", {"id": re.compile(r"pa_color|pa_colours?", re.I)})
                if color_select:
                    p.colors = [opt.text.strip() for opt in color_select.find_all("option") if opt.get("value")]

            # Always try to extract gallery images from actual img src attributes
            gallery_imgs = soup.select(".woocommerce-product-gallery__image img, .product-gallery img")
            if gallery_imgs:
                all_imgs = []
                for img_tag in gallery_imgs[:5]:
                    src = img_tag.get("src") or img_tag.get("data-src") or img_tag.get("data-large_image", "")
                    if src and "placeholder" not in src:
                        all_imgs.append(urljoin(url, src))
                if all_imgs:
                    p.images = all_imgs

            # Extract rich product details from page content
            if not p.details:
                p.details = _extract_rich_details(soup)

            # If description is too short, try to get a better one
            if len(p.description) < 50:
                short_desc = _extract_short_description(soup)
                if short_desc and len(short_desc) > len(p.description):
                    p.description = short_desc

    # Deduplicate by name
    unique = []
    for p in products:
        key = p.name.lower().strip()
        if key and key not in seen_names:
            seen_names.add(key)
            p.source_hash = hashlib.sha256(p.url.encode()).hexdigest() if p.url else hashlib.sha256(p.name.encode()).hexdigest()
            unique.append(p)

    return unique


def _extract_rich_details(soup: BeautifulSoup) -> str:
    """
    Extract rich product details from WooCommerce tab panels,
    product descriptions, and additional info sections.
    Returns a combined text with fabric, fit, construction, care details.
    """
    parts = []

    # 1. Full description from WooCommerce tab panel
    tab_panels = soup.select(".woocommerce-Tabs-panel--description, .woocommerce-Tabs-panel")
    for panel in tab_panels:
        text = panel.get_text(separator=" ", strip=True)
        # Clean up WP CSS class artifacts that leak into text
        text = re.sub(r'\[&[^\]]*\]', '', text)
        text = re.sub(r'p\]:[\w-]+', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > 30 and text not in [p for p in parts]:
            parts.append(text)

    # 2. Product content / description div
    for selector in [
        ".product-description",
        ".woocommerce-product-details__short-description",
        ".product_description",
        ".entry-content",
        "[itemprop='description']",
    ]:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(separator=" ", strip=True)
            text = re.sub(r'\s+', ' ', text).strip()
            if len(text) > 30 and text not in parts:
                parts.append(text)

    # 3. Additional information table (materials, dimensions, etc.)
    additional = soup.select_one(".woocommerce-Tabs-panel--additional_information, .additional-information")
    if additional:
        rows = additional.select("tr")
        info_parts = []
        for row in rows:
            th = row.select_one("th")
            td = row.select_one("td")
            if th and td:
                label = th.get_text(strip=True)
                value = td.get_text(separator=", ", strip=True)
                if label and value:
                    info_parts.append(f"{label}: {value}")
        if info_parts:
            parts.append("Additional info: " + "; ".join(info_parts))

    # 4. Key features / bullet points
    for selector in [".product-features", ".key-features", ".features-list"]:
        el = soup.select_one(selector)
        if el:
            items = el.select("li")
            if items:
                features = [li.get_text(strip=True) for li in items if li.get_text(strip=True)]
                if features:
                    parts.append("Key features: " + "; ".join(features))

    combined = " | ".join(parts)
    # Limit to 2000 chars to avoid bloating the DB
    return combined[:2000] if combined else ""


def _extract_short_description(soup: BeautifulSoup) -> str:
    """Extract the short product description."""
    el = soup.select_one(".woocommerce-product-details__short-description")
    if el:
        text = el.get_text(separator=" ", strip=True)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:500]
    return ""


def _parse_price(price_str: str | None) -> float | None:
    """Parse a price string to float."""
    if not price_str:
        return None
    cleaned = re.sub(r'[^\d.,]', '', str(price_str))
    if not cleaned:
        return None
    if ',' in cleaned and '.' in cleaned:
        cleaned = cleaned.replace(',', '')
    elif ',' in cleaned:
        parts = cleaned.split(',')
        if len(parts[-1]) == 2:
            cleaned = cleaned.replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_jsonld(html: str, url: str) -> list[ProductData]:
    """Extract products from JSON-LD Schema.org data."""
    products = []
    soup = BeautifulSoup(html, "html.parser")

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            if data.get("@graph"):
                items = data["@graph"]
            else:
                items = [data]

        for item in items:
            if not isinstance(item, dict):
                continue
            item_type = item.get("@type", "")
            if isinstance(item_type, list):
                item_type = item_type[0] if item_type else ""

            if item_type.lower() != "product":
                continue

            name = item.get("name", "")
            if not name:
                continue

            price = None
            currency = ""
            original_price = None
            in_stock = True

            offers = item.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            if isinstance(offers, dict):
                price = _parse_price(offers.get("price"))
                currency = offers.get("priceCurrency", "")
                if price is None:
                    price_spec = offers.get("priceSpecification", {})
                    if isinstance(price_spec, list):
                        price_spec = price_spec[0] if price_spec else {}
                    if isinstance(price_spec, dict):
                        price = _parse_price(price_spec.get("price"))
                        if not currency:
                            currency = price_spec.get("priceCurrency", "")
                availability = offers.get("availability", "")
                if "OutOfStock" in str(availability):
                    in_stock = False

            images = []
            img = item.get("image", [])
            if isinstance(img, str):
                images = [img]
            elif isinstance(img, list):
                images = [i if isinstance(i, str) else i.get("url", "") for i in img]
                images = [i for i in images if i]
            images = [urljoin(url, i) for i in images]

            brand = ""
            brand_data = item.get("brand", {})
            if isinstance(brand_data, dict):
                brand = brand_data.get("name", "")
            elif isinstance(brand_data, str):
                brand = brand_data

            products.append(ProductData(
                name=name,
                description=item.get("description", "")[:1000],
                price=price,
                currency=currency,
                original_price=original_price,
                images=images[:5],
                url=url,
                sku=str(item.get("sku", "")),
                brand=brand,
                category=item.get("category", ""),
                in_stock=in_stock,
            ))

    return products


def _extract_opengraph(html: str, url: str) -> ProductData | None:
    """Extract product from Open Graph meta tags."""
    soup = BeautifulSoup(html, "html.parser")

    og_type = ""
    og_title = ""
    og_image = ""
    og_description = ""
    product_price = None
    product_currency = ""

    for meta in soup.find_all("meta"):
        prop = meta.get("property", "") or meta.get("name", "")
        content = meta.get("content", "")
        if prop == "og:type":
            og_type = content
        elif prop == "og:title":
            og_title = content
        elif prop == "og:image":
            og_image = content
        elif prop == "og:description":
            og_description = content
        elif prop in ("product:price:amount", "og:price:amount"):
            product_price = _parse_price(content)
        elif prop in ("product:price:currency", "og:price:currency"):
            product_currency = content

    if og_type == "product" and og_title:
        return ProductData(
            name=og_title,
            description=og_description[:1000],
            price=product_price,
            currency=product_currency,
            images=[urljoin(url, og_image)] if og_image else [],
            url=url,
        )

    return None


def _extract_shopify(html: str, url: str) -> list[ProductData]:
    """Extract products from Shopify's embedded product JSON."""
    products = []

    patterns = [
        re.compile(r'var\s+meta\s*=\s*(\{.*?"product".*?\});', re.DOTALL),
        re.compile(r'"product"\s*:\s*(\{[^;]+\})\s*[,;]', re.DOTALL),
    ]

    for pattern in patterns:
        match = pattern.search(html)
        if not match:
            continue
        try:
            data = json.loads(match.group(1))
            product_data = data.get("product", data) if isinstance(data, dict) else None
            if not product_data or not isinstance(product_data, dict):
                continue

            name = product_data.get("title", "")
            if not name:
                continue

            sizes = set()
            colors = set()
            price = None
            for variant in product_data.get("variants", []):
                if isinstance(variant, dict):
                    if not price:
                        price = _parse_price(variant.get("price"))
                    opt1 = variant.get("option1", "")
                    opt2 = variant.get("option2", "")
                    for opt in [opt1, opt2]:
                        if opt and re.match(r'^(XXS|XS|S|M|L|XL|XXL|XXXL|\d+)$', str(opt), re.IGNORECASE):
                            sizes.add(str(opt))
                        elif opt:
                            colors.add(str(opt))

            images = []
            for img in product_data.get("images", [])[:5]:
                if isinstance(img, str):
                    images.append(img)
                elif isinstance(img, dict):
                    images.append(img.get("src", ""))

            products.append(ProductData(
                name=name,
                description=product_data.get("description", "")[:1000],
                price=price,
                currency="",
                images=[i for i in images if i],
                url=url,
                brand=product_data.get("vendor", ""),
                category=product_data.get("type", ""),
                sizes=sorted(sizes),
                colors=sorted(colors),
                tags=product_data.get("tags", [])[:10] if isinstance(product_data.get("tags"), list) else [],
            ))
        except (json.JSONDecodeError, KeyError, TypeError):
            continue

    return products
