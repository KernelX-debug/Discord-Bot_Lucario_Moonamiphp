from __future__ import annotations

from dataclasses import dataclass

import requests

from moonani_utils import (
    build_session,
    extract_coords_from_html,
    extract_country_code,
    html_to_text,
    match_priority,
    normalize_name,
)

POKEMON_URL = "https://moonani.com/PokeList/ajax.php?page=pokemon&action=load"
POKEMON_REFERER = "https://moonani.com/PokeList/index.php"


@dataclass(slots=True)
class PokemonSpawn:
    name: str
    number: str
    coords: str
    cp: str
    level: str
    attack: str
    defense: str
    hp: str
    shiny: bool
    start_time: str
    end_time: str
    country: str

    @property
    def maps_url(self) -> str:
        return f"https://maps.google.com/?q={self.coords}"

    @property
    def alert_key(self) -> str:
        return f"{normalize_name(self.name)}|{self.coords}|{self.end_time}"


def _parse_spawn(item: dict) -> PokemonSpawn | None:
    coords = extract_coords_from_html(item.get("Coords", ""))

    if not coords:
        return None

    return PokemonSpawn(
        name=html_to_text(item.get("Name", "")),
        number=str(item.get("Number", "")).strip(),
        coords=coords,
        cp=str(item.get("CP", "")).strip(),
        level=str(item.get("Level", "")).strip(),
        attack=str(item.get("Attack", "")).strip(),
        defense=str(item.get("Defense", "")).strip(),
        hp=str(item.get("HP", "")).strip(),
        shiny=str(item.get("Shiny", "")).strip().lower() == "yes",
        start_time=str(item.get("Start Time", "")).strip(),
        end_time=str(item.get("End Time", "")).strip(),
        country=extract_country_code(item.get("Country", "")),
    )


def fetch_hundo_pokemon(
    timeout: int = 20,
    page_size: int = 100,
    max_scan_records: int = 10000,
) -> list[PokemonSpawn]:
    session = build_session(POKEMON_REFERER)
    session.headers["Content-Type"] = "application/x-www-form-urlencoded"

    results: list[PokemonSpawn] = []
    scanned = 0
    start = 0
    draw = 1

    while scanned < max_scan_records:
        length = min(page_size, max_scan_records - scanned)
        payload = {
            "iv": 100,
            "pvp": 0,
            "pokemons": "",
            "start": start,
            "length": length,
            "draw": draw,
        }

        response = session.post(POKEMON_URL, data=payload, timeout=timeout)
        response.raise_for_status()

        data = response.json().get("data", [])

        if not data:
            break

        for item in data:
            spawn = _parse_spawn(item)
            if spawn is not None:
                results.append(spawn)

        batch_size = len(data)
        scanned += batch_size
        start += batch_size
        draw += 1

        if batch_size < length:
            break

    return results


def search_hundo_pokemon(
    name: str,
    timeout: int = 20,
    page_size: int = 100,
    max_scan_records: int = 10000,
    limit: int = 5,
) -> list[PokemonSpawn]:
    query = normalize_name(name)
    matches: list[tuple[int, PokemonSpawn]] = []

    for spawn in fetch_hundo_pokemon(
        timeout=timeout,
        page_size=page_size,
        max_scan_records=max_scan_records,
    ):
        priority = match_priority(query, normalize_name(spawn.name))
        if priority is not None:
            matches.append((priority, spawn))

    matches.sort(
        key=lambda item: (
            item[0],
            item[1].name.lower(),
            item[1].end_time,
            item[1].coords,
        )
    )

    return [spawn for _, spawn in matches[:limit]]


if __name__ == "__main__":
    try:
        for pokemon in search_hundo_pokemon("snivy", limit=5):
            print("=" * 60)
            print(f"Pokemon : {pokemon.name} #{pokemon.number}")
            print(f"CP/Nvl  : {pokemon.cp} / {pokemon.level}")
            print(
                "IV      : "
                f"{pokemon.attack}/{pokemon.defense}/{pokemon.hp}"
            )
            print(f"Coords  : {pokemon.coords}")
            print(f"Country : {pokemon.country}")
            print(f"Start   : {pokemon.start_time}")
            print(f"End     : {pokemon.end_time}")
            print(f"Maps    : {pokemon.maps_url}")
    except requests.RequestException as exc:
        print(f"Error: {exc}")
