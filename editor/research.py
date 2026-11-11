from __future__ import annotations

import html
import re
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from PIL import Image
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HEADERS = {"User-Agent": "IllustratedDocumentaryAI/1.0 (local documentary research workflow)"}
WIKIPEDIA_API = "https://{language}.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
IMAGE_HOSTS = {"upload.wikimedia.org", "thumb.wikimedia.org"}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
SESSION.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=3,
            connect=3,
            read=2,
            status=3,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
        )
    ),
)


def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    response = SESSION.get(url, params=params, timeout=(10, 30))
    response.raise_for_status()
    return response.json()


def _plain_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", value)).split())


def _metadata_value(metadata: dict[str, Any], key: str) -> str:
    value = metadata.get(key, {})
    return _plain_text(value.get("value", "")) if isinstance(value, dict) else ""


def _wikipedia_sources(query: str, language: str) -> list[dict[str, str]]:
    api = WIKIPEDIA_API.format(language=language)
    results = _get_json(
        api,
        {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": query,
            "srlimit": 3,
            "srprop": "snippet",
        },
    ).get("query", {}).get("search", [])
    if not results:
        return []

    page_ids = "|".join(str(item["pageid"]) for item in results)
    pages = _get_json(
        api,
        {
            "action": "query",
            "format": "json",
            "pageids": page_ids,
            "prop": "extracts|info",
            "exintro": 1,
            "explaintext": 1,
            "exchars": 1600,
            "inprop": "url",
        },
    ).get("query", {}).get("pages", {})
    by_id = {int(page_id): page for page_id, page in pages.items()}

    sources = []
    for result in results:
        page = by_id.get(int(result["pageid"]), {})
        extract = " ".join(str(page.get("extract", "")).split())
        if extract:
            sources.append(
                {
                    "title": str(page.get("title", result.get("title", ""))),
                    "url": str(page.get("fullurl", "")),
                    "extract": extract,
                }
            )
    return sources


def _commons_images(query: str, limit: int = 8) -> list[dict[str, Any]]:
    search = _get_json(
        COMMONS_API,
        {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": 6,
            "gsrlimit": limit,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|size|mime",
            "iiurlwidth": 1920,
            "iiextmetadatamultilang": 0,
        },
    )
    pages = search.get("query", {}).get("pages", {})
    candidates = []
    for page in pages.values():
        info_list = page.get("imageinfo", [])
        if not info_list:
            continue
        info = info_list[0]
        if not str(info.get("mime", "")).startswith("image/"):
            continue
        image_url = info.get("thumburl") or info.get("url")
        if not _is_allowed_image_url(image_url):
            continue
        metadata = info.get("extmetadata", {})
        artist = _metadata_value(metadata, "Artist") or _metadata_value(metadata, "Credit")
        license_name = _metadata_value(metadata, "LicenseShortName")
        candidates.append(
            {
                "title": str(page.get("title", "")),
                "image_url": str(image_url),
                "source_url": str(info.get("descriptionurl", "")),
                "artist": artist,
                "license": license_name,
                "license_url": _metadata_value(metadata, "LicenseUrl"),
                "width": int(info.get("width", 0)),
                "height": int(info.get("height", 0)),
            }
        )
    return candidates


def _is_allowed_image_url(url: Any) -> bool:
    if not isinstance(url, str):
        return False
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in IMAGE_HOSTS


def download_commons_image(candidate: dict[str, Any], destination: Path) -> None:
    url = candidate.get("image_url")
    if not _is_allowed_image_url(url):
        raise ValueError("Image URL is not a Wikimedia Commons upload URL")

    with SESSION.get(url, timeout=(10, 60), stream=True) as response:
        response.raise_for_status()
        if not response.headers.get("Content-Type", "").startswith("image/"):
            raise ValueError("Wikimedia returned a non-image response")
        content_length = int(response.headers.get("Content-Length", 0))
        if content_length > 25 * 1024 * 1024:
            raise ValueError("Image is larger than 25 MB")
        content = BytesIO()
        total_bytes = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            total_bytes += len(chunk)
            if total_bytes > 25 * 1024 * 1024:
                raise ValueError("Image is larger than 25 MB")
            content.write(chunk)

    content.seek(0)
    with Image.open(content) as image:
        if image.width * image.height > 40_000_000:
            raise ValueError("Image dimensions are too large to safely process")
        image.verify()
    content.seek(0)
    with Image.open(content) as image:
        image = image.convert("RGB")
        image.thumbnail((2560, 1440), Image.Resampling.LANCZOS)
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, "PNG")


def research_scene(query: str, language: str = "English") -> dict[str, Any]:
    term = " ".join((query or "").split())
    if not term:
        return {"query": "", "sources": [], "image_candidates": [], "selected_image": 0}

    wiki_language = "hi" if language.lower().startswith("hindi") else "en"
    errors = []
    sources: list[dict[str, str]] = []
    images: list[dict[str, Any]] = []
    try:
        sources = _wikipedia_sources(term, wiki_language)
    except (requests.RequestException, ValueError, KeyError) as exc:
        errors.append(f"Wikipedia: {exc}")
    try:
        images = _commons_images(term)
    except (requests.RequestException, ValueError, KeyError) as exc:
        errors.append(f"Wikimedia Commons: {exc}")

    return {
        "query": term,
        "sources": sources,
        "image_candidates": images,
        "selected_image": 0,
        "research_note": "Search results are references for review, not independent fact-checking.",
        "errors": errors,
    }


def image_credit(candidate: dict[str, Any]) -> str:
    parts = [candidate.get("title", "Wikimedia Commons image")]
    if candidate.get("artist"):
        parts.append(f"by {candidate['artist']}")
    if candidate.get("license"):
        parts.append(candidate["license"])
    if candidate.get("source_url"):
        parts.append(candidate["source_url"])
    if candidate.get("license_url"):
        parts.append(candidate["license_url"])
    return " | ".join(str(part) for part in parts if part)
