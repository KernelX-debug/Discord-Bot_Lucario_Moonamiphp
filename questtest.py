import re
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


def limpiar_texto(texto):
    return re.sub(r"\s+", " ", texto).strip()


def obtener_quests():
    response = session.get(URL, timeout=20)

    if response.status_code != 200:
        print(f"[!] Error HTTP: {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    filas = soup.find_all("tr")

    quests = []

    for fila in filas:
        columnas = fila.find_all("td")

        # Saltar filas inválidas
        if len(columnas) < 6:
            continue

        try:
            pokemon = limpiar_texto(columnas[0].get_text())
            pokemon_id = limpiar_texto(columnas[1].get_text())
            quest = limpiar_texto(columnas[2].get_text())
            coords = limpiar_texto(columnas[3].get_text())
            fecha_inicio = limpiar_texto(columnas[4].get_text())
            fecha_fin = limpiar_texto(columnas[5].get_text())

            # País opcional
            pais = "Desconocido"
            if len(columnas) >= 7:
                pais = limpiar_texto(columnas[6].get_text())

            # Validar coordenadas
            if "," not in coords:
                continue

            lat, lon = coords.split(",", 1)

            maps = f"https://maps.google.com/?q={lat},{lon}"

            quests.append({
                "pokemon": pokemon,
                "pokemon_id": pokemon_id,
                "quest": quest,
                "coords": coords,
                "inicio": fecha_inicio,
                "fin": fecha_fin,
                "pais": pais.upper(),
                "maps": maps
            })

        except Exception:
            continue

    return quests


def mostrar_quests(quests):
    print("\n")
    print("=" * 75)
    print("                    POKÉMON GO QUEST SCANNER")
    print("=" * 75)

    print(f"\n[+] Quests encontradas: {len(quests)}\n")

    for i, q in enumerate(quests, start=1):

        print("╔" + "═" * 70 + "╗")
        print(f"║ QUEST #{i}".ljust(71) + "║")
        print("╠" + "═" * 70 + "╣")

        print(f"║ Pokémon      : {q['pokemon']}".ljust(71) + "║")
        print(f"║ Pokémon ID   : {q['pokemon_id']}".ljust(71) + "║")
        print(f"║ Quest        : {q['quest']}".ljust(71) + "║")
        print(f"║ Coordenadas  : {q['coords']}".ljust(71) + "║")
        print(f"║ País         : {q['pais']}".ljust(71) + "║")
        print(f"║ Inicio       : {q['inicio']}".ljust(71) + "║")
        print(f"║ Expira       : {q['fin']}".ljust(71) + "║")
        print(f"║ Google Maps  : {q['maps']}".ljust(71) + "║")

        print("╚" + "═" * 70 + "╝")
        print()

    print(f"[✓] Total mostrado: {len(quests)} quests")


if __name__ == "__main__":
    try:
        quests = obtener_quests()

        if quests:
            mostrar_quests(quests)
        else:
            print("[!] No se encontraron quests.")

    except Exception as e:
        print(f"[!] Error: {e}")
