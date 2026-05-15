import html
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import requests


DATA_CLIPBOARD_RE = re.compile(r'data-clipboard-text="([^"]+)"')
HTML_TAG_RE = re.compile(r"<[^>]+>")
SRC_RE = re.compile(r'src="([^"]+)"')
IV_RE = re.compile(r"(\d+)")
FLAG_RE = re.compile(r"/flags/([a-z]{2})\.png", re.IGNORECASE)
TABLE_BODY_RE = re.compile(r"<tbody>(.*?)</tbody>", re.IGNORECASE | re.DOTALL)
TABLE_ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
TABLE_CELL_RE = re.compile(r"<td>(.*?)</td>", re.IGNORECASE | re.DOTALL)


@dataclass
class PokemonSpawn:
    name: str
    number: str
    coords: str
    cp: int
    level: int
    attack: int
    defense: int
    hp: int
    iv_percent: int
    shiny: bool
    start_time: str
    end_time: str
    country: str
    image_url: str

    @property
    def maps_url(self) -> str:
        return f"https://maps.google.com/?q={self.coords}"

    @property
    def is_zero_iv(self) -> bool:
        return self.attack == 0 and self.defense == 0 and self.hp == 0

    @property
    def unique_key(self) -> str:
        return "|".join(
            [
                self.number,
                self.coords,
                self.start_time,
                self.end_time,
                str(self.attack),
                str(self.defense),
                str(self.hp),
            ]
        )


def _strip_html(value: str) -> str:
    return HTML_TAG_RE.sub("", html.unescape(value or "")).strip()


def _normalize_name(value: str) -> str:
    cleaned = _strip_html(value).lower()
    normalized = unicodedata.normalize("NFKD", cleaned)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _extract_coords(value: str) -> str:
    match = DATA_CLIPBOARD_RE.search(value or "")
    if match:
        return html.unescape(match.group(1)).strip()
    return _strip_html(value)


def _extract_image_url(value: str) -> str:
    match = SRC_RE.search(value or "")
    return match.group(1).strip() if match else ""


def _extract_iv_percent(value: str) -> int:
    match = IV_RE.search(_strip_html(value))
    return int(match.group(1)) if match else 0


def _extract_country(value: str) -> str:
    text_value = _strip_html(value)
    if text_value:
        return text_value

    flag_match = FLAG_RE.search(value or "")
    if flag_match:
        return flag_match.group(1).upper()

    return "Unknown"


def _safe_int(value: Any) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


class MoonaniClient:
    def __init__(
        self,
        endpoint: str = "https://moonani.com/PokeList/ajax.php?page=pokemon&action=load",
        referer: str = "https://moonani.com/PokeList/index.php",
        iv0_page_url: str = "https://moonani.com/PokeList/iv0.php",
        timeout: int = 20,
        cache_ttl_seconds: int = 45,
        resolve_missing_countries: bool = False,
        geocoder_endpoint: str = "https://nominatim.openstreetmap.org/reverse",
        geocoder_user_agent: str = "Lucario Discord Bot/1.0",
    ) -> None:
        self.endpoint = endpoint
        self.referer = referer
        self.iv0_page_url = iv0_page_url
        self.timeout = timeout
        self.cache_ttl_seconds = cache_ttl_seconds
        self.resolve_missing_countries = resolve_missing_countries
        self.geocoder_endpoint = geocoder_endpoint
        self.geocoder_user_agent = geocoder_user_agent
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Referer": self.referer,
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Lucario Discord Bot)",
            }
        )
        self._page_cache = {}  # type: Dict[Tuple[int, int, int, int], Tuple[float, Dict[str, Any]]]
        self._country_cache = {}  # type: Dict[str, str]
        self._geocoder_backoff_until = 0.0
        self._iv0_cache = None  # type: Optional[Tuple[float, List[PokemonSpawn]]]

    def _fetch_page(self, start: int, length: int, iv_filter: int, pvp: int) -> Dict[str, Any]:
        cache_key = (start, length, iv_filter, pvp)
        now = time.monotonic()
        cached = self._page_cache.get(cache_key)
        if cached and now - cached[0] < self.cache_ttl_seconds:
            return cached[1]

        payload = {
            "iv": iv_filter,
            "pvp": pvp,
            "pokemons": "",
            "start": start,
            "length": length,
            "draw": 1,
        }

        response = self.session.post(self.endpoint, data=payload, timeout=self.timeout)
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, dict) or "data" not in data:
            raise ValueError("Moonani respondio con un formato inesperado.")

        self._page_cache[cache_key] = (now, data)
        return data

    def _fetch_iv0_page(self) -> List[PokemonSpawn]:
        now = time.monotonic()
        if self._iv0_cache and now - self._iv0_cache[0] < self.cache_ttl_seconds:
            return self._iv0_cache[1]

        response = self.session.get(self.iv0_page_url, timeout=self.timeout)
        response.raise_for_status()

        spawns = self._parse_iv0_page(response.text)
        self._iv0_cache = (now, spawns)
        return spawns

    def _parse_iv0_page(self, page_html: str) -> List[PokemonSpawn]:
        body_match = TABLE_BODY_RE.search(page_html)
        if not body_match:
            raise ValueError("No pude encontrar la tabla de IV 0 en la pagina de Moonani.")

        rows_html = body_match.group(1)
        spawns = []  # type: List[PokemonSpawn]

        for row_html in TABLE_ROW_RE.findall(rows_html):
            clean_row_html = re.sub(r"<!--.*?-->", "", row_html, flags=re.DOTALL)
            cells = TABLE_CELL_RE.findall(clean_row_html)
            if len(cells) < 14:
                continue

            spawn = PokemonSpawn(
                name=_strip_html(cells[1]),
                number=_strip_html(cells[2]),
                coords=_extract_coords(cells[3]),
                cp=_safe_int(_strip_html(cells[4])),
                level=_safe_int(_strip_html(cells[5])),
                attack=_safe_int(_strip_html(cells[6])),
                defense=_safe_int(_strip_html(cells[7])),
                hp=_safe_int(_strip_html(cells[8])),
                iv_percent=_extract_iv_percent(cells[9]),
                shiny=_strip_html(cells[10]).lower() == "yes",
                start_time=_strip_html(cells[11]),
                end_time=_strip_html(cells[12]),
                country=_extract_country(cells[13]),
                image_url=_extract_image_url(cells[1]),
            )

            if spawn.country == "Unknown" and self.resolve_missing_countries:
                spawn.country = self.lookup_country_by_coords(spawn.coords)

            spawns.append(spawn)

        return spawns

    def parse_row(self, row: Dict[str, Any]) -> PokemonSpawn:
        coords = _extract_coords(str(row.get("Coords", "")))
        country = _extract_country(str(row.get("Country", "")))
        if country == "Unknown" and self.resolve_missing_countries:
            country = self.lookup_country_by_coords(coords)

        return PokemonSpawn(
            name=_strip_html(row.get("Name", "")),
            number=str(row.get("Number", "")).strip(),
            coords=coords,
            cp=_safe_int(row.get("CP")),
            level=_safe_int(row.get("Level")),
            attack=_safe_int(row.get("Attack")),
            defense=_safe_int(row.get("Defense")),
            hp=_safe_int(row.get("HP")),
            iv_percent=_extract_iv_percent(str(row.get("IV", ""))),
            shiny=str(row.get("Shiny", "")).strip().lower() == "yes",
            start_time=str(row.get("Start Time", "")).strip(),
            end_time=str(row.get("End Time", "")).strip(),
            country=country,
            image_url=_extract_image_url(str(row.get("Name", ""))),
        )

    def lookup_country_by_coords(self, coords: str) -> str:
        cached_country = self._country_cache.get(coords)
        if cached_country:
            return cached_country
        if time.monotonic() < self._geocoder_backoff_until:
            return "Unknown"

        try:
            lat_text, lon_text = [item.strip() for item in coords.split(",", 1)]
            lat = float(lat_text)
            lon = float(lon_text)
        except (AttributeError, ValueError):
            return "Unknown"

        params = {
            "format": "jsonv2",
            "lat": lat,
            "lon": lon,
            "zoom": 3,
            "addressdetails": 1,
        }
        headers = {
            "User-Agent": self.geocoder_user_agent,
            "Accept-Language": "en",
        }

        try:
            response = self.session.get(
                "{}?{}".format(self.geocoder_endpoint, urlencode(params)),
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            address = payload.get("address", {}) if isinstance(payload, dict) else {}
            country = str(address.get("country", "")).strip() or "Unknown"
        except requests.RequestException:
            self._geocoder_backoff_until = time.monotonic() + 300
            return "Unknown"

        self._country_cache[coords] = country
        return country

    def search_pokemon(
        self,
        query: str = "",
        limit: int = 5,
        iv_filter: int = 100,
        shiny_only: bool = False,
        pvp: int = 0,
        page_size: int = 100,
        max_records: Optional[int] = 10000,
    ) -> List[PokemonSpawn]:
        if limit < 1:
            raise ValueError("El limite debe ser mayor que cero.")
        if not 0 <= iv_filter <= 100:
            raise ValueError("El filtro IV debe estar entre 0 y 100.")
        if page_size < 1:
            raise ValueError("El tamano de pagina debe ser mayor que cero.")

        normalized_query = _normalize_name(query)
        results = []  # type: List[PokemonSpawn]

        start = 0
        total_records = None  # type: Optional[int]

        while total_records is None or start < total_records:
            if max_records is not None and start >= max_records:
                break

            page = self._fetch_page(start=start, length=page_size, iv_filter=iv_filter, pvp=pvp)
            rows = page.get("data", [])
            total_records = _safe_int(page.get("recordsFiltered"))

            if not rows:
                break

            for row in rows:
                spawn = self.parse_row(row)

                if normalized_query and normalized_query not in _normalize_name(spawn.name):
                    continue
                if shiny_only and not spawn.shiny:
                    continue
                if spawn.iv_percent < iv_filter:
                    continue

                results.append(spawn)
                if len(results) >= limit:
                    return results

            start += len(rows)

        return results

    def search_zero_iv_pokemon(self, query: str = "", limit: int = 5) -> List[PokemonSpawn]:
        if limit < 1:
            raise ValueError("El limite debe ser mayor que cero.")

        normalized_query = _normalize_name(query)
        results = []  # type: List[PokemonSpawn]

        for spawn in self._fetch_iv0_page():
            if normalized_query and normalized_query not in _normalize_name(spawn.name):
                continue
            if not spawn.is_zero_iv:
                continue

            results.append(spawn)
            if len(results) >= limit:
                break

        return results

    def list_current_hundo_spawns(self, limit: int = 250, page_size: int = 100, max_records: Optional[int] = 2000) -> List[PokemonSpawn]:
        return self.search_pokemon(
            query="",
            limit=limit,
            iv_filter=100,
            shiny_only=False,
            pvp=0,
            page_size=page_size,
            max_records=max_records,
        )

    def list_current_zero_iv_spawns(self, limit: int = 250) -> List[PokemonSpawn]:
        spawns = self._fetch_iv0_page()
        exact_zero = [spawn for spawn in spawns if spawn.is_zero_iv]
        return exact_zero[:limit]
