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

QUEST_URL = "https://moonani.com/PokeList/quest.php"
QUEST_REFERER = "https://moonani.com/PokeList/"

QUEST_AUTOCOMPLETE_NAMES = [
    "Kecleon",
    "Pikachu",
    "Psyduck",
    "Snorlax",
    "Spinda",
]

ALLOWED_QUEST_NAMES = {
    "kecleon": {"kecleon"},
    "pikachu": {"pikachu"},
    "psyduck": {"psyduck"},
    "snorlax": {"snorlax"},
    "spinda": {"spinda 00", "spinda 07", "spinda"},
    "spinda 00": {"spinda 00"},
    "spinda 07": {"spinda 07"},
}


@dataclass(slots=True)
class QuestEncounter:
    pokemon: str
    pokemon_id: str
    quest: str
    coords: str
    start_time: str
    end_time: str
    country: str

    @property
    def maps_url(self) -> str:
        return f"https://maps.google.com/?q={self.coords}"


def fetch_quest_data(timeout: int = 20) -> list[QuestEncounter]:
    session = build_session(QUEST_REFERER)
    response = session.get(QUEST_URL, timeout=timeout)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    quests: list[QuestEncounter] = []

    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 7:
            continue

        coords = extract_coords_from_tag(cells[3])
        if not coords:
            continue

        quests.append(
            QuestEncounter(
                pokemon=html_to_text(str(cells[0])),
                pokemon_id=html_to_text(str(cells[1])),
                quest=html_to_text(str(cells[2])),
                coords=coords,
                start_time=html_to_text(str(cells[4])),
                end_time=html_to_text(str(cells[5])),
                country=extract_country_code(str(cells[6])),
            )
        )

    return quests


def normalize_quest_query(query: str) -> str:
    normalized = normalize_name(query)
    if normalized.startswith("spinda"):
        if "00" in normalized:
            return "spinda 00"
        if "07" in normalized:
            return "spinda 07"
        return "spinda"
    return normalized


def search_quests(
    query: str,
    timeout: int = 20,
    limit: int = 8,
) -> list[QuestEncounter]:
    normalized_query = normalize_quest_query(query)
    allowed_names = ALLOWED_QUEST_NAMES.get(normalized_query)

    if not allowed_names:
        return []

    matches: list[tuple[int, QuestEncounter]] = []

    for quest in fetch_quest_data(timeout=timeout):
        priority = match_priority(
            normalized_query if normalized_query != "spinda" else "spinda",
            normalize_name(quest.pokemon),
        )

        if priority is None:
            continue

        if normalize_name(quest.pokemon) not in allowed_names:
            continue

        matches.append((priority, quest))

    matches.sort(
        key=lambda item: (
            item[0],
            item[1].pokemon.lower(),
            item[1].end_time,
            item[1].coords,
        )
    )

    return [quest for _, quest in matches[:limit]]


if __name__ == "__main__":
    try:
        for quest in search_quests("spinda"):
            print("=" * 60)
            print(f"Pokemon : {quest.pokemon} #{quest.pokemon_id}")
            print(f"Quest   : {quest.quest}")
            print(f"Coords  : {quest.coords}")
            print(f"Country : {quest.country}")
            print(f"Start   : {quest.start_time}")
            print(f"End     : {quest.end_time}")
            print(f"Maps    : {quest.maps_url}")
    except requests.RequestException as exc:
        print(f"Error: {exc}")
