import html
import re

import requests


def extraer_coords(texto):
    match = re.search(r'data-clipboard-text="([^"]+)"', texto)
    return match.group(1) if match else ""


def limpiar_nombre(texto):
    # Primero decodifica entidades HTML (&#9792; -> ♀, &#9794; -> ♂)
    texto = html.unescape(texto)
    # Luego elimina las etiquetas HTML
    texto = re.sub(r"<[^>]+>", "", texto)
    # Limpia espacios extra
    return texto.strip()


def extraer_pais(texto):
    texto = html.unescape(texto)
    texto = re.sub(r"<[^>]+>", "", texto).strip()
    return texto if texto else "??"


url = "https://moonani.com/PokeList/ajax.php?page=pokemon&action=load"
payload = {
    "iv": 100,
    "pvp": 0,
    "pokemons": "",
    "start": 0,
    "length": 230,  # todos los registros visibles del bloque solicitado
    "draw": 1,
}
headers = {
    "Referer": "https://moonani.com/PokeList/index.php",
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "Mozilla/5.0",
}

r = requests.post(url, data=payload, headers=headers, timeout=20)
r.raise_for_status()
data = r.json().get("data", [])

print(f"Total pokémones recibidos: {len(data)}\n")

for p in data:
    nombre = limpiar_nombre(p["Name"])
    coords = extraer_coords(p["Coords"])
    shiny = "✨ SHINY" if p["Shiny"] == "Yes" else ""
    pais = extraer_pais(p["Country"])

    print(f"{'=' * 50}")
    print(f"🎯 {nombre} #{p['Number']} {shiny}")
    print(f"📍 {coords}")
    print(f"⚡ CP: {p['CP']} | Nivel: {p['Level']}")
    print(f"💪 ATK:{p['Attack']} DEF:{p['Defense']} HP:{p['HP']}")
    print(f"⏱️  Inicio: {p['Start Time']}")
    print(f"⏱️  Fin:    {p['End Time']}")
    print(f"🌍 País: {pais}")
    print(f"🗺️  https://maps.google.com/?q={coords}")
