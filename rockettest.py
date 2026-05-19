import re
import time
import random
import requests
from bs4 import BeautifulSoup

URL = "https://moonani.com/PokeList/rocket.php"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://moonani.com/PokeList/",
}

ROCKET_NAMES = [
    "Arlo",
    "Cliff",
    "Sierra",
    "Giovanni",
]

COORDS_REGEX = re.compile(r"(-?\d+\.\d+,-?\d+\.\d+)")

session = requests.Session()
session.headers.update(HEADERS)


def get_rocket_data():
    # Delay para parecer más humano
    time.sleep(random.uniform(1.5, 3.5))

    response = session.get(URL, timeout=20)

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    rockets = []

    # Buscar todas las filas de la tabla
    rows = soup.find_all("tr")

    for row in rows:
        row_text = row.get_text(" ", strip=True)

        # Buscar coordenadas
        coords_match = COORDS_REGEX.search(str(row))

        if not coords_match:
            continue

        coords = coords_match.group(1)

        # Detectar líder Rocket
        rocket_leader = None

        for name in ROCKET_NAMES:
            if name.lower() in row_text.lower():
                rocket_leader = name
                break

        # Detectar tipo elemental
        rocket_type = None

        type_match = re.search(
            r"(Grass|Fire|Water|Electric|Ice|Ground|Rock|Psychic|Ghost|Dark|Steel|Fairy|Dragon|Poison|Bug|Flying|Fighting|Normal)",
            row_text,
            re.IGNORECASE,
        )

        if type_match:
            rocket_type = type_match.group(1).title()

        # Detectar país
        country = None

        flag_match = re.search(
            r'flags/([a-z]{2})\.png',
            str(row),
            re.IGNORECASE,
        )

        if flag_match:
            country = flag_match.group(1).upper()

        rockets.append(
            {
                "leader": rocket_leader,
                "type": rocket_type,
                "coords": coords,
                "country": country,
                "maps_url": f"https://maps.google.com/?q={coords}",
            }
        )

    return rockets


if __name__ == "__main__":
    try:
        rocket_data = get_rocket_data()

        print(f"\nSe encontraron {len(rocket_data)} Rockets:\n")

        for rocket in rocket_data:
            print("=" * 50)
            print(f"Líder   : {rocket['leader']}")
            print(f"Tipo    : {rocket['type']}")
            print(f"Coords  : {rocket['coords']}")
            print(f"País    : {rocket['country']}")
            print(f"Maps    : {rocket['maps_url']}")

    except Exception as e:
        print(f"Error: {e}")
