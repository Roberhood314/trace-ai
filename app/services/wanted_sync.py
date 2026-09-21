import hashlib
import re
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

async def fetch_official_wanted(max_pages: int = 3) -> tuple[list[dict], int]:
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

    return list(all_records.values()), len(visited)

def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
