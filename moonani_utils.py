from __future__ import annotations

import html
import re
import unicodedata

import requests
from bs4 import Tag

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

COORDS_REGEX = re.compile(r'data-clipboard-text="([^"]+)"')
FLAG_REGEX = re.compile(r"flags/([a-z]{2})\.png", re.IGNORECASE)
TAG_REGEX = re.compile(r"<[^>]+>")
SPACE_REGEX = re.compile(r"\s+")
GENDER_REGEX = re.compile(r"[♀♂]")
NON_ALNUM_REGEX = re.compile(r"[^a-z0-9]+")


def build_session(referer: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    session.headers["Referer"] = referer
    return session


def clean_whitespace(value: str) -> str:
    return SPACE_REGEX.sub(" ", value).strip()


def html_to_text(value: str) -> str:
    decoded = html.unescape(value or "")
    without_tags = TAG_REGEX.sub(" ", decoded)
    return clean_whitespace(without_tags)


def extract_coords_from_html(value: str) -> str:
    match = COORDS_REGEX.search(value or "")
    return match.group(1).strip() if match else ""


def extract_coords_from_tag(tag: Tag) -> str:
    button = tag.find(attrs={"data-clipboard-text": True})
    if button is None:
        return ""
    return str(button.get("data-clipboard-text", "")).strip()


def extract_country_code(value: str) -> str:
    match = FLAG_REGEX.search(value or "")
    if match:
        return match.group(1).upper()

    text = html_to_text(value).upper()
    return text or "N/A"


def normalize_name(value: str) -> str:
    collapsed = html_to_text(value).lower()
    collapsed = GENDER_REGEX.sub("", collapsed)
    collapsed = unicodedata.normalize("NFKD", collapsed)
    collapsed = "".join(
        char for char in collapsed if not unicodedata.combining(char)
    )
    collapsed = NON_ALNUM_REGEX.sub(" ", collapsed)
    return clean_whitespace(collapsed)


def match_priority(query: str, candidate: str) -> int | None:
    query = clean_whitespace(query)
    candidate = clean_whitespace(candidate)

    if not query or not candidate:
        return None
    if candidate == query:
        return 0
    if candidate.startswith(query):
        return 1
    if f" {query}" in candidate or f"{query} " in candidate:
        return 2
    if query in candidate:
        return 3
    return None
