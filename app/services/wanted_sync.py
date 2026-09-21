import asyncio
import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

OFFICIAL_WANTED_URL = "https://truyna.bocongan.gov.vn/%C4%90%E1%BB%91i-t%C6%B0%E1%BB%A3ng-truy-n%C3%A3"
SOURCE_NAME = "Cổng thông tin truy nã - Bộ Công an"

def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())

def _source_key(detail_url: str | None, cells: list[str]) -> str:
    raw = detail_url or "|".join(cells)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _ascii_text(value: str | None) -> str:
    text = unicodedata.normalize("NFD", _clean(value)).lower()
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")

def parse_wanted_detail(html: str, page_url: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    image_url = None
    candidates: list[tuple[int, str]] = []
    for img in soup.find_all("img"):
        raw_src = img.get("src") or img.get("data-src") or img.get("data-original")
        if not raw_src:
            continue
        src = urljoin(page_url, raw_src)
        marker = " ".join([
            _ascii_text(img.get("alt")),
            _ascii_text(img.get("title")),
            _ascii_text(img.get("class") if isinstance(img.get("class"), str) else " ".join(img.get("class") or [])),
            _ascii_text(img.get("id")),
        ])
        src_key = _ascii_text(src)
        score = 0
        if "anh doi tuong truy na" in marker:
            score += 100
        if "truy na" in marker:
            score += 40
        if any(k in src_key for k in ("truyna", "truy-na", "doituong", "doi-tuong", "wanted")):
            score += 20
        if any(k in src_key for k in ("logo", "icon", "banner", "avatar-default", "no-image")):
            score -= 80
        width = str(img.get("width") or "")
        height = str(img.get("height") or "")
        if width.isdigit() and int(width) >= 120:
            score += 5
        if height.isdigit() and int(height) >= 120:
            score += 5
        candidates.append((score, src))
    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        if candidates[0][0] > 0:
            image_url = candidates[0][1]

    danger_level = None
    for tr in soup.find_all("tr"):
        cells = [_clean(td.get_text(" ", strip=True)) for td in tr.find_all(["th", "td"])]
        for i, value in enumerate(cells[:-1]):
            if value == "Loại truy nã":
                kind = cells[i + 1].lower()
                if "đặc biệt" in kind or "nguy hiểm" in kind:
                    danger_level = "cao"
                elif kind:
                    danger_level = "khong_ro"
                break
        if danger_level:
            break

    return {"image_url": image_url, "danger_level": danger_level}

def parse_wanted_page(html: str, page_url: str) -> tuple[list[dict], list[str]]:
    soup = BeautifulSoup(html, "lxml")
    records: list[dict] = []

    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        for tr in rows:
            cells = tr.find_all("td")
            if len(cells) < 8:
                continue
            values = [_clean(td.get_text(" ", strip=True)) for td in cells[:8]]
            if not values[0].isdigit():
                continue

            name_cell = cells[1]
            anchor = name_cell.find("a", href=True)
            detail_url = urljoin(page_url, anchor["href"]) if anchor else None

            birth_year = None
            if re.fullmatch(r"\d{4}", values[2]):
                birth_year = int(values[2])

            record = {
                "source_key": _source_key(detail_url, values),
                "full_name": values[1],
                "birth_year": birth_year,
                "registered_address": values[3] or None,
                "parents": values[4] or None,
                "offense": values[5] or None,
                "warrant_reference": values[6] or None,
                "issuing_unit": values[7] or None,
                "detail_url": detail_url,
                "source_url": page_url,
                "source_name": SOURCE_NAME,
            }
            if record["full_name"]:
                records.append(record)

    next_pages: list[str] = []
    for a in soup.find_all("a", href=True):
        text = _clean(a.get_text(" ", strip=True))
        href = urljoin(page_url, a["href"])
        if (text.isdigit() or text in {">", ">>"}) and "truyna.bocongan.gov.vn" in href:
            next_pages.append(href)

    seen = set()
    unique_pages = []
    for item in next_pages:
        if item not in seen and item != page_url:
            seen.add(item)
            unique_pages.append(item)

    return records, unique_pages

async def fetch_official_wanted(max_pages: int = 3, detail_limit: int = 40) -> tuple[list[dict], int]:
    max_pages = max(1, min(int(max_pages), 10))
    queue = [OFFICIAL_WANTED_URL]
    visited: set[str] = set()
    all_records: dict[str, dict] = {}

    headers = {
        "User-Agent": "TRACE-AI/1.0 (+authorized public-data sync; source attribution retained)",
        "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.6",
    }

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=headers) as client:
        while queue and len(visited) < max_pages:
            url = queue.pop(0)
            if url in visited:
                continue
            response = await client.get(url)
            response.raise_for_status()
            visited.add(str(response.url))
            records, discovered = parse_wanted_page(response.text, str(response.url))
            for record in records:
                all_records[record["source_key"]] = record
            for next_url in discovered:
                if next_url not in visited and next_url not in queue:
                    queue.append(next_url)

        records = list(all_records.values())
        sem = asyncio.Semaphore(5)

        async def enrich(record: dict):
            detail_url = record.get("detail_url")
            if not detail_url:
                return
            async with sem:
                try:
                    response = await client.get(detail_url)
                    response.raise_for_status()
                    record.update(parse_wanted_detail(response.text, str(response.url)))
                except httpx.HTTPError:
                    record.setdefault("image_url", None)
                    record.setdefault("danger_level", None)

        detail_candidates = [r for r in records if r.get("detail_url")][:max(0, min(int(detail_limit), 100))]
        await asyncio.gather(*(enrich(r) for r in detail_candidates))

    return list(all_records.values()), len(visited)

def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
