from __future__ import annotations

from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

from moonani_utils import (
    build_session,
    extract_coords_from_tag,
    extract_country_code,
    html_to_text,
    match_priority,
    normalize_name,
)

RAID_URL = "https://moonani.com/PokeList/raid.php"
RAID_REFERER = "https://moonani.com/PokeList/"


@dataclass(slots=True)
class RaidEncounter:
    name: str
    number: str
    level: str
    coords: str
    start_time: str
    end_time: str
    country: str

    @property
    def maps_url(self) -> str:
        return f"https://maps.google.com/?q={self.coords}"


def fetch_raid_data(timeout: int = 20) -> list[RaidEncounter]:
    session = build_session(RAID_REFERER)
    response = session.get(RAID_URL, timeout=timeout)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    raids: list[RaidEncounter] = []

    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 7:
            continue

        coords = extract_coords_from_tag(cells[3])
        if not coords:
            continue

        raids.append(
            RaidEncounter(
                name=html_to_text(str(cells[0])),
                number=html_to_text(str(cells[1])),
                level=html_to_text(str(cells[2])),
                coords=coords,
                start_time=html_to_text(str(cells[4])),
                end_time=html_to_text(str(cells[5])),
                country=extract_country_code(str(cells[6])),
            )
        )

    return raids


def search_raids(
    query: str,
    timeout: int = 20,
    limit: int = 8,
) -> list[RaidEncounter]:
    normalized_query = normalize_name(query)
    matches: list[tuple[int, RaidEncounter]] = []

    for raid in fetch_raid_data(timeout=timeout):
        priority = match_priority(normalized_query, normalize_name(raid.name))
        if priority is not None:
            matches.append((priority, raid))

    matches.sort(
        key=lambda item: (
            item[0],
            item[1].name.lower(),
            item[1].end_time,
            item[1].coords,
        )
    )

    return [raid for _, raid in matches[:limit]]


if __name__ == "__main__":
    try:
        for raid in search_raids("rayquaza"):
            print("=" * 60)
            print(f"Raid    : {raid.name}")
            print(f"Level   : {raid.level}")
            print(f"Coords  : {raid.coords}")
            print(f"Country : {raid.country}")
            print(f"Start   : {raid.start_time}")
            print(f"End     : {raid.end_time}")
            print(f"Maps    : {raid.maps_url}")
    except requests.RequestException as exc:
        print(f"Error: {exc}")
