import asyncio
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

OFFICIAL_WANTED_URL = "https://truyna.bocongan.gov.vn/%C4%90%E1%BB%91i-t%C6%B0%E1%BB%A3ng-truy-n%C3%A3"
OFFICIAL_SUSPENDED_URL = "https://truyna.bocongan.gov.vn/%C4%90%E1%BB%91i-t%C6%B0%E1%BB%A3ng-%C4%91%C3%ACnh-n%C3%A3"
SOURCE_NAME = "Cổng thông tin truy nã - Bộ Công an"


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _ascii_text(value: str | None) -> str:
    text = unicodedata.normalize("NFD", _clean(value)).lower()
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def _source_record_id(detail_url: str | None) -> str | None:
    if not detail_url:
        return None
    m = re.search(r"/ma/([0-9a-fA-F-]{16,})", detail_url)
    if m:
        return m.group(1).lower()
    parsed = urlparse(detail_url)
    m = re.search(r"([0-9a-fA-F]{8}-[0-9a-fA-F-]{27,})", parsed.path)
    return m.group(1).lower() if m else None


def _source_key(detail_url: str | None, cells: list[str]) -> str:
    stable_id = _source_record_id(detail_url)
    raw = stable_id or detail_url or "|".join(cells)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def record_checksum(record: dict) -> str:
    fields = (
        "source_record_id", "full_name", "birth_year", "registered_address",
        "parents", "offense", "warrant_reference", "issuing_unit",
        "detail_url", "image_url", "danger_level", "status",
    )
    payload = {k: record.get(k) for k in fields}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
        if any(k in src_key for k in ("truyna", "truy-na", "doituong", "doi-tuong", "wanted", "showimage")):
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


def parse_wanted_page(html: str, page_url: str, status: str = "active") -> tuple[list[dict], list[str]]:
    soup = BeautifulSoup(html, "lxml")
    records: list[dict] = []

    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) < 8:
                continue
            values = [_clean(td.get_text(" ", strip=True)) for td in cells[:8]]
            if not values[0].isdigit():
                continue

            anchor = cells[1].find("a", href=True)
            detail_url = urljoin(page_url, anchor["href"]) if anchor else None
            birth_year = int(values[2]) if re.fullmatch(r"\d{4}", values[2]) else None
            source_record_id = _source_record_id(detail_url)

            record = {
                "source_key": _source_key(detail_url, values),
                "source_record_id": source_record_id,
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
                "status": status,
            }
            record["checksum"] = record_checksum(record)
            if record["full_name"]:
                records.append(record)

    next_pages: list[str] = []
    for a in soup.find_all("a", href=True):
        text = _clean(a.get_text(" ", strip=True))
        href = urljoin(page_url, a["href"])
        if (text.isdigit() or text in {">", ">>", "Tiếp", "Cuối"}) and "truyna.bocongan.gov.vn" in href:
            next_pages.append(href)

    unique_pages: list[str] = []
    seen = set()
    for item in next_pages:
        if item not in seen and item != page_url:
            seen.add(item)
            unique_pages.append(item)
    return records, unique_pages


def _dnn_page_meta(html: str, page_url: str) -> tuple[int, str | None, dict[str, str], str]:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    match = re.search(r"Page\s+(\d+)\s+of\s+(\d+)", text, re.I)
    total_pages = int(match.group(2)) if match else 1

    pager_target = None
    for a in soup.find_all("a", href=True):
        href = a.get("href") or ""
        m = re.search(r"__doPostBack\('([^']+)','(\d+)'\)", href)
        if m:
            pager_target = m.group(1)
            break

    form = soup.find("form", id="Form")
    hidden: dict[str, str] = {}
    action_url = page_url
    if form:
        for inp in form.find_all("input", {"type": "hidden"}):
            name = inp.get("name")
            if name:
                hidden[name] = inp.get("value", "")
        action = form.get("action")
        if action:
            action_url = urljoin(page_url, action)

    return total_pages, pager_target, hidden, action_url


async def iter_official_list_pages(
    start_url: str,
    status: str,
    max_pages: int = 250,
):
    """Yield one parsed DNN page at a time so callers can commit incrementally."""
    max_pages = max(1, min(int(max_pages), 500))
    headers = {
        "User-Agent": "TRACE-AI/1.5 (+official public-data sync; source attribution retained)",
        "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.6",
    }

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=headers) as client:
        response = await client.get(start_url)
        response.raise_for_status()
        current_url = str(response.url)

        records, _ = parse_wanted_page(response.text, current_url, status=status)
        total_pages, pager_target, hidden, action_url = _dnn_page_meta(response.text, current_url)
        pages_to_fetch = min(total_pages, max_pages)
        yield 1, total_pages, records

        if pages_to_fetch <= 1 or not pager_target:
            return

        for page_number in range(2, pages_to_fetch + 1):
            form_fields = dict(hidden)
            form_fields["__EVENTTARGET"] = pager_target
            form_fields["__EVENTARGUMENT"] = str(page_number)
            multipart = {name: (None, value) for name, value in form_fields.items()}

            response = await client.post(
                action_url,
                files=multipart,
                headers={"Referer": current_url},
            )
            response.raise_for_status()
            current_url = str(response.url)

            page_match = re.search(r"Page\s+(\d+)\s+of\s+(\d+)", response.text, re.I)
            if page_match and int(page_match.group(1)) != page_number:
                raise RuntimeError(
                    f"official pagination state mismatch: expected={page_number};got={page_match.group(1)}"
                )

            records, _ = parse_wanted_page(response.text, current_url, status=status)
            yield page_number, total_pages, records

            next_total, next_target, next_hidden, next_action = _dnn_page_meta(response.text, current_url)
            if next_target:
                pager_target = next_target
            if next_hidden:
                hidden = next_hidden
            if next_action:
                action_url = next_action
            if next_total:
                total_pages = next_total


async def fetch_official_list(
    start_url: str,
    status: str,
    max_pages: int = 250,
) -> tuple[list[dict], int]:
    all_records: dict[str, dict] = {}
    visited_pages = 0
    async for page_number, total_pages, records in iter_official_list_pages(
        start_url, status, max_pages=max_pages
    ):
        visited_pages = page_number
        for record in records:
            all_records[record["source_key"]] = record
    return list(all_records.values()), visited_pages


async def fetch_official_wanted(
    max_pages: int = 250,
    detail_limit: int = 0,
    include_suspended: bool = True,
    suspended_pages: int | None = None,
) -> tuple[list[dict], int]:
    active_records, active_pages = await fetch_official_list(
        OFFICIAL_WANTED_URL, "active", max_pages=max_pages
    )
    combined = {r["source_key"]: r for r in active_records}
    total_pages = active_pages

    if include_suspended:
        suspended_records, fetched = await fetch_official_list(
            OFFICIAL_SUSPENDED_URL,
            "dinh_na",
            max_pages=suspended_pages or max_pages,
        )
        total_pages += fetched
        for record in suspended_records:
            combined[record["source_key"]] = record

    records = list(combined.values())

    # Detail enrichment is intentionally bounded. Full sync stays list-first;
    # images and missing detail metadata are loaded on demand by the image endpoint.
    detail_limit = max(0, min(int(detail_limit), 200))
    if detail_limit:
        sem = asyncio.Semaphore(4)
        headers = {
            "User-Agent": "TRACE-AI/1.4 (+official public-data detail sync)",
            "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.6",
        }
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=headers) as client:
            async def enrich(record: dict):
                detail_url = record.get("detail_url")
                if not detail_url:
                    return
                async with sem:
                    try:
                        response = await client.get(detail_url)
                        response.raise_for_status()
                        record.update(parse_wanted_detail(response.text, str(response.url)))
                        record["checksum"] = record_checksum(record)
                    except httpx.HTTPError:
                        pass

            candidates = [r for r in records if r.get("detail_url")][:detail_limit]
            await asyncio.gather(*(enrich(r) for r in candidates))

    return records, total_pages


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
