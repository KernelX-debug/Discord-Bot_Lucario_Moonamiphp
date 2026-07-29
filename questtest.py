import re
import unicodedata
from typing import Dict, List

import requests
from bs4 import BeautifulSoup


URL = "https://moonani.com/PokeList/quest.php"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://moonani.com/PokeList/",
}

session = requests.Session()
session.headers.update(HEADERS)


def limpiar_texto(texto: str) -> str:
    return re.sub(r"\s+", " ", texto or "").strip()


def normalizar_texto(texto: str) -> str:
    texto = limpiar_texto(texto).lower()
    normalized = unicodedata.normalize("NFKD", texto)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def extraer_coords(columna) -> str:
    boton = columna.find(attrs={"data-clipboard-text": True})
    if boton:
        return limpiar_texto(str(boton.get("data-clipboard-text", "")))
    return limpiar_texto(columna.get_text())


def obtener_quests(timeout: int = 20) -> List[Dict[str, str]]:
    response = session.get(URL, timeout=timeout)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    quests = []

    for fila in soup.find_all("tr"):
        columnas = fila.find_all("td")
        if len(columnas) < 7:
            continue

        pokemon = limpiar_texto(columnas[0].get_text())
        coords = extraer_coords(columnas[3])

        if not pokemon or "," not in coords:
            continue

        quests.append(
            {
                "pokemon": pokemon,
                "pokemon_id": limpiar_texto(columnas[1].get_text()),
                "quest": limpiar_texto(columnas[2].get_text()),
                "coords": coords,
                "inicio": limpiar_texto(columnas[4].get_text()),
                "fin": limpiar_texto(columnas[5].get_text()),
                "pais": limpiar_texto(columnas[6].get_text()).upper() or "N/D",
                "maps": f"https://maps.google.com/?q={coords}",
            }
        )

    return quests


def search_quests(nombre: str, limit: int = 5, timeout: int = 20) -> List[Dict[str, str]]:
    query = normalizar_texto(nombre)
    if not query:
        return []

    results = []
    for quest in obtener_quests(timeout=timeout):
        if query not in normalizar_texto(quest["pokemon"]):
            continue

        results.append(quest)
        if len(results) >= limit:
            break

    return results


if __name__ == "__main__":
    for quest in search_quests("lapras", limit=10):
        print("=" * 60)
        print(f"Pokemon : {quest['pokemon']} #{quest['pokemon_id']}")
        print(f"Quest   : {quest['quest']}")
        print(f"Coords  : {quest['coords']}")
        print(f"Pais    : {quest['pais']}")
        print(f"Inicio  : {quest['inicio']}")
        print(f"Fin     : {quest['fin']}")
        print(f"Maps    : {quest['maps']}")
