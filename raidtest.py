import re
import time
import random
import requests
from bs4 import BeautifulSoup

URL = "https://moonani.com/PokeList/raid.php"

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


def clean_text(value):
    return re.sub(r"\s+", " ", value).strip()


def get_raid_data():

    time.sleep(random.uniform(1.5, 3.5))

    response = session.get(URL, timeout=20)

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    raids = []

    rows = soup.find_all("tr")

    for row in rows:

        cells = row.find_all("td")

        # Validar columnas mínimas
        if len(cells) < 7:
            continue

        try:

            # =========================
            # NOMBRE RAID
            # =========================
            raid_name = clean_text(
                cells[0].get_text(" ", strip=True)
            )

            # =========================
            # NIVEL RAID
            # =========================
            level = clean_text(
                cells[2].get_text(" ", strip=True)
            )

            # =========================
            # COORDENADAS
            # =========================
            coords_button = cells[3].find(
                attrs={"data-clipboard-text": True}
            )

            if not coords_button:
                continue

            coords = coords_button[
                "data-clipboard-text"
            ].strip()

            # =========================
            # PAÍS
            # =========================
            country_match = re.search(
                r'flags/([a-z]{2})\.png',
                str(cells[6]),
                re.IGNORECASE
            )

            country = (
                country_match.group(1).upper()
                if country_match else "N/A"
            )

            raids.append(
                {
                    "raid_name": raid_name,
                    "level": level,
                    "coords": coords,
                    "country": country,
                    "maps_url": (
                        f"https://maps.google.com/?q={coords}"
                    ),
                }
            )

        except Exception:
            continue

    return raids


if __name__ == "__main__":

    try:

        raid_data = get_raid_data()

        print(f"\nSe encontraron {len(raid_data)} Raids:\n")

        for raid in raid_data:

            print("=" * 60)

            print(f"Raid         : {raid['raid_name']}")
            print(f"Nivel        : {raid['level']}")
            print(f"Coords       : {raid['coords']}")
            print(f"País         : {raid['country']}")
            print(f"Maps         : {raid['maps_url']}")

    except Exception as e:

        print(f"Error: {e}")