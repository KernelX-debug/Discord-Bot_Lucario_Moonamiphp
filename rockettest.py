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

ROCKET_URL = "https://moonani.com/PokeList/rocket.php"
ROCKET_REFERER = "https://moonani.com/PokeList/"

ROCKET_LEADERS = {"arlo", "cliff", "sierra", "giovanni"}


@dataclass(slots=True)
class RocketEncounter:
    name: str
    power: str
    coords: str
    start_time: str
    end_time: str
    country: str
    leader: str | None
    grunt_type: str | None

    @property
    def maps_url(self) -> str:
        return f"https://maps.google.com/?q={self.coords}"


def fetch_rocket_data(timeout: int = 20) -> list[RocketEncounter]:
    session = build_session(ROCKET_REFERER)
    response = session.get(ROCKET_URL, timeout=timeout)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    rockets: list[RocketEncounter] = []

    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 8:
            continue

        name = html_to_text(str(cells[1]))
        coords = extract_coords_from_tag(cells[3])

        if not name or not coords:
            continue

        normalized = normalize_name(name)
        leader = name if normalized in ROCKET_LEADERS else None
        grunt_type = None if leader else name

        rockets.append(
            RocketEncounter(
                name=name,
                power=html_to_text(str(cells[2])),
                coords=coords,
                start_time=html_to_text(str(cells[5])),
                end_time=html_to_text(str(cells[6])),
                country=extract_country_code(str(cells[7])),
                leader=leader,
                grunt_type=grunt_type,
            )
        )

    return rockets


def search_rockets(
    query: str,
    timeout: int = 20,
    limit: int = 8,
) -> list[RocketEncounter]:
    normalized_query = normalize_name(query)
    matches: list[tuple[int, RocketEncounter]] = []

    for rocket in fetch_rocket_data(timeout=timeout):
        candidates = [
            normalize_name(rocket.name),
            normalize_name(rocket.leader or ""),
            normalize_name(rocket.grunt_type or ""),
        ]

        priorities = [
            priority
            for priority in (
                match_priority(normalized_query, candidate)
                for candidate in candidates
            )
            if priority is not None
        ]

        if priorities:
            matches.append((min(priorities), rocket))

    matches.sort(
        key=lambda item: (
            item[0],
            item[1].name.lower(),
            item[1].end_time,
            item[1].coords,
        )
    )

    return [rocket for _, rocket in matches[:limit]]


if __name__ == "__main__":
    try:
        for rocket in search_rockets("giovanni"):
            print("=" * 60)
            print(f"Rocket  : {rocket.name}")
            print(f"Power   : {rocket.power}")
            print(f"Coords  : {rocket.coords}")
            print(f"Country : {rocket.country}")
            print(f"Start   : {rocket.start_time}")
            print(f"End     : {rocket.end_time}")
            print(f"Maps    : {rocket.maps_url}")
    except requests.RequestException as exc:
        print(f"Error: {exc}")
