# 🤖 Lucario - Moonani Discord Pokemon Go Coordinates Bot
![Discord](https://img.shields.io/badge/-Discord-5865F2?style=flat-square&logo=discord&logoColor=ffffff)
![Python](https://img.shields.io/badge/-Python-3776AB?style=flat-square&logo=python&logoColor=ffffff)

Bot de Discord en Python que consulta el endpoint de Moonani PokeList para obtener apariciones de Pokemon iv100 y iv0; extrae coordenadas y las publica en Discord mediante comandos.

## Que hace este proyecto. ¿A que quiero llegar?

- Consulta el endpoint `https://moonani.com/PokeList/ajax.php?page=pokemon&action=load`
- Limpia el HTML que devuelve Moonani en campos como nombre, IV, coordenadas y pais
- Extrae coordenadas listas para copiar y pegar, además de link redirigido a google maps.
- Permite buscar por nombre parcial
- De momento solo filtra los pokemones iv100 y iv0
- Responde en Discord con mensajes compactos

## Estructura del proyecto

- `discord_bot.py`: punto de entrada del bot y definicion de comandos
- `moonani_client.py`: cliente HTTP y logica de parseo/filtrado de resultados
- `test_pokelist_limpio.py`: script base limpio usado para validar la idea original
- `.env`: variables de entorno (No compartir estos datos con terceros)
- `requirements.txt`: dependencias del proyecto

## Comandos disponibles en discord
**Comandos para todos los usuarios de discord**
- `/ping`: verifica si el bot esta en linea
- `/pokemon`: muestra resultados con formato enriquecido para pokemones iv100
- `/pokemon0`: muestra resultados en formato enriquecido para pokemones iv0
- `/coords`: devuelve coordenadas en formato compacto para copiar para pokemones iv100
- `/coords0`: devuelve coordenadas en formato compacto para copiar para pokemones iv0

**Comandos para uso administrativo en discord (permisos de administrador)**

- `/configurar_canal`: permite configurar un canal específico para enviar alertas de pokemones iv100/iv0 de forma constante y actualizada
- `/quitar_canal`: permite quitar el canal configurado para las alertas de pokemones iv100/iv0
- `/ver_canales`: muestra los canales configurados para alertas automáticas
- `/agregar_seguimiento`: agrega alertas de un pokemón específico iv100 en un canal
- `/quitar_seguimiento`: quitar alertas de un pokemón específico iv100 del canal
- `/ver_seguimiento`: ver todos los seguimientos de pokémon iv100 configurados

## Requisitos

- Python 3.13 recomendado
- Un bot creado en el [Discord Developer Portal](https://discord.com/developers/applications)

## Prueba de funcionamiento breve para pokemones

Antes de usar el bot de Discord, es posible validar desde cero la extraccion y el parseo de datos del endpoint de Moonani con un script independiente. Esta prueba no requiere clonar el repositorio completo ni configurar Discord.

### 1. Crear una carpeta de trabajo

```powershell
mkdir prueba_moonani
cd prueba_moonani
```
### 2. Crear el archivo test_pokelist_limpio.py
Crea un archivo llamado `test_pokelist_limpio.py` con este contenido:

```python
import requests
import re
import html

def extraer_coords(texto):
    match = re.search(r'data-clipboard-text="([^"]+)"', texto)
    return match.group(1) if match else ""

def limpiar_nombre(texto):
    # Primero decodifica entidades HTML (&#9792; -> ♀, &#9794; -> ♂)
    texto = html.unescape(texto)
    # Luego elimina las etiquetas HTML
    texto = re.sub(r'<[^>]+>', '', texto)
    # Limpia espacios extra
    return texto.strip()

def extraer_pais(texto):
    texto = html.unescape(texto)
    texto = re.sub(r'<[^>]+>', '', texto).strip()
    return texto if texto else "??"

url = "https://moonani.com/PokeList/ajax.php?page=pokemon&action=load"
payload = {
    "iv": 100,
    "pvp": 0,
    "pokemons": "",
    "start": 0,
    "length": 230,
    "draw": 1
}
headers = {
    "Referer": "https://moonani.com/PokeList/index.php",
    "Content-Type": "application/x-www-form-urlencoded"
}

r = requests.post(url, data=payload, headers=headers)
data = r.json().get("data", [])

print(f"Total pokémones recibidos: {len(data)}\n")

for p in data:
    nombre = limpiar_nombre(p["Name"])
    coords = extraer_coords(p["Coords"])
    shiny  = "✨ SHINY" if p["Shiny"] == "Yes" else ""
    pais   = extraer_pais(p["Country"])

    print(f"{'='*50}")
    print(f"🎯 {nombre} #{p['Number']} {shiny}")
    print(f"📍 {coords}")
    print(f"⚡ CP: {p['CP']} | Nivel: {p['Level']}")
    print(f"💪 ATK:{p['Attack']} DEF:{p['Defense']} HP:{p['HP']}")
    print(f"⏱️  Inicio: {p['Start Time']}")
    print(f"⏱️  Fin:    {p['End Time']}")
    print(f"🌍 País: {pais}")
    print(f"🗺️  https://maps.google.com/?q={coords}")
```
### 3. Instalar la dependencia necesaria

```powershell
py -3.13 -m pip install requests
```

### 4. Ejecutar la prueba

```powershell
py -3.13 test_pokelist_limpio.py
```
## Resultado esperado
- Se realiza una peticion HTTP directa al endpoint de Moonani.
- Se procesa la respuesta JSON recibida.
- Se limpia el HTML embebido en campos como Name, Coords y Country.
- Se imprime en consola una lista de pokémones con nombre, coordenadas, CP, nivel, stats, tiempo de aparicion y enlace de Google Maps.
- Esta prueba permite verificar de forma tecnica que el endpoint responde correctamente y que el parseo base funciona antes de integrar la logica en el bot de Discord.

## Imagen de referencia

<p align="center">
  <img src="assets/testmoonami.png" alt="test de moonami" width="100%">
</p>

## Prueba de funcionamiento breve para rockets

Antes de usar el bot de Discord, es posible validar desde cero la extraccion y el parseo de datos de Moonani con un script independiente. Esta prueba no requiere clonar el repositorio completo ni configurar Discord.

### 1. Crear una carpeta de trabajo

```powershell
mkdir prueba_rockets_moonani
cd prueba_rockets_moonani
```

### 2. Instalar dependencias necesarias

```powershell
pip install requests beautifulsoup4
```

### 3. Crear el archivo rocket_bot.py

```powershell
New-Item rocket_bot.py -ItemType File
```

### 4. Modifica el archivo en el bloc de notas nativo de windows

```powershell
notepad rocket_bot.py
```

**Pega el siguiente contenido:**

```python
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

COORDS_REGEX = re.compile(r"(-?\d+\.\d+,-?\d+\.\d+)")

session = requests.Session()
session.headers.update(HEADERS)


def clean_text(value):
    return value.strip().replace("\n", " ").replace("\t", " ")


def get_rocket_data():
    time.sleep(random.uniform(1.5, 3.5))

    response = session.get(URL, timeout=20)

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    rockets = []

    rows = soup.find_all("tr")

    for row in rows:
        cells = row.find_all("td")

        # Saltar filas vacías o incompletas
        if len(cells) < 7:
            continue

        try:
            # Nombre/tipo rocket
            rocket_type = clean_text(cells[0].get_text())

            # Número ID
            number = clean_text(cells[1].get_text())

            # Coordenadas
            coords_match = COORDS_REGEX.search(str(cells[2]))

            if not coords_match:
                continue

            coords = coords_match.group(1)

            # Start Time
            start_time = clean_text(cells[4].get_text())

            # End Time
            end_time = clean_text(cells[5].get_text())

            # País
            country = clean_text(cells[6].get_text()).upper()

            rockets.append(
                {
                    "rocket_type": rocket_type,
                    "number": number,
                    "coords": coords,
                    "start_time": start_time,
                    "end_time": end_time,
                    "country": country,
                    "maps_url": f"https://maps.google.com/?q={coords}",
                }
            )

        except Exception:
            continue

    return rockets


if __name__ == "__main__":
    try:
        rocket_data = get_rocket_data()

        print(f"\nSe encontraron {len(rocket_data)} Rockets:\n")

        for rocket in rocket_data:
            print("=" * 60)
            print(f"Tipo Rocket : {rocket['rocket_type']}")
            print(f"Número      : {rocket['number']}")
            print(f"Coords       : {rocket['coords']}")
            print(f"Inicio       : {rocket['start_time']}")
            print(f"Fin          : {rocket['end_time']}")
            print(f"País         : {rocket['country']}")
            print(f"Maps         : {rocket['maps_url']}")

    except Exception as e:
        print(f"Error: {e}")
```

**ES IMPORTANTE GUARDAR EL CONTENIDO DEL BLOC DE NOTAS CON `ctrl+g` O DESDE ARCHIVO/GUARDAR**

### 5. Ejecuta el script de python

```powershell
python rocket_bot.py
```

## Resultado esperado

* Se realiza una petición HTTP directa a la página Rocket de Moonani.
* Se procesa el HTML recibido utilizando BeautifulSoup.
* Se extraen y limpian los datos embebidos en la tabla de Rockets.
* Se detectan correctamente los tipos Rocket y los líderes Rocket (Arlo, Cliff, Sierra y Giovanni).
* Se extraen las coordenadas desde los atributos `data-clipboard-text`.
* Se obtienen correctamente los tiempos de inicio y finalización de cada Rocket.
* Se imprime en consola una lista organizada con tipo Rocket, líder Rocket, coordenadas, país, tiempo de aparición, tiempo de expiración y enlace de Google Maps.
* Esta prueba permite verificar técnicamente que la página responde correctamente y que el parseo base funciona antes de integrar la lógica en el bot de Discord.


## Imagen de referencia

<p align="center">
  <img src="assets/testrocket.png" alt="test de rocket" width="100%">
</p>

## Instalacion para uso como bot de discord
### Clonar el repositorio

```powershell
git clone https://github.com/KernelX-debug/Discord-Bot_Lucario_Moonamiphp.git
cd Discord-Bot_Lucario_Moonamiphp
```
### Modificar archivos e instalar dependencias

1. En la carpeta del proyecto.

```powershell
cd Discord-Bot_Lucario_Moonamiphp
```

2. Instala las dependencias.

```powershell
py -3.13 -m pip install -r requirements.txt
```

3. Modifica el archivo `.env`.
```powershell
@"
DISCORD_BOT_TOKEN=pega_aqui_el_token_de_tu_bot
DISCORD_GUILD_ID=
MOONANI_TIMEOUT=20
MOONANI_PAGE_SIZE=100
MOONANI_MAX_SCAN_RECORDS=10000
MOONANI_RESOLVE_COUNTRIES=false
MOONANI_GEOCODER_ENDPOINT=
MOONANI_GEOCODER_USER_AGENT=Lucario Discord Bot/1.0
LUCARIO_SETTINGS_PATH=lucario_guild_settings.json
LUCARIO_MONITOR_INTERVAL_SECONDS=45
LUCARIO_ALERT_LIMIT_100IV=250
LUCARIO_ALERT_LIMIT_0IV=250
"@ | Set-Content .env

```

## Significado de las variables

- `DISCORD_BOT_TOKEN`: token privado de tu bot
- `DISCORD_GUILD_ID`: opcional, acelera la aparicion de comandos slash en un servidor concreto
- `MOONANI_TIMEOUT`: tiempo maximo de espera para peticiones HTTP
- `MOONANI_PAGE_SIZE`: cuantos registros pedir por bloque al endpoint
- `MOONANI_MAX_SCAN_RECORDS`: limite maximo de registros a revisar en una busqueda
- `MOONANI_RESOLVE_COUNTRIES`: intenta dar el pais desde coordenadas cuando Moonani no lo devuelve (EN MANTENIMIENTO POR LÍMITE DE SOLICITUDES{e409}, USAR "false" POR DEFECTO)
- `MOONANI_GEOCODER_ENDPOINT`: endpoint de reverse geocoding
- `MOONANI_GEOCODER_USER_AGENT`: identificador HTTP para el geocoder
- `LUCARIO_SETTINGS_PATH=lucario_guild_settings.json`: variables del id de servidor y canales de discord asignados para enviar coordenadas iv100/iv0
- `LUCARIO_MONITOR_INTERVAL_SECONDS=45`: polling constante definido en 45seconds
- `LUCARIO_ALERT_LIMIT_100IV=250`: límite de alertas de 100iv por momentos.
- `LUCARIO_ALERT_LIMIT_0IV=250`: límite de alertas de 0iv por momentos.
## Ejecucion

```powershell
py -3.13 discord_bot.py
```

## Ejemplos de uso

```text
/pokemon nombre:wiglett cantidad:3
/coords nombre:pikachu cantidad:5
```

## Funcionamiento

<p align="center">
  <img src="assets/pikipeksearch.png" alt="Busqueda de Pikipek" width="45%">
  <img src="assets/lucariosearch.png" alt="Busqueda de Lucario" width="45%">
</p>

## Como invitar el bot a tu servidor

1. Abre tu aplicacion en el [Discord Developer Portal](https://discord.com/developers/applications).
2. Ve a `OAuth2` > `URL Generator`.
3. Marca los scopes `bot` y `applications.commands`.
4. Concede permisos como `View Channels`, `Send Messages`, `Embed Links` y `Read Message History`.
5. Abre el enlace generado y selecciona tu servidor.

## Mejoras futuras

- Agregar búsqueda de misiones/recompensa pokemón
- Utilizando el endpoint se puede acceder a más filtros de pokemones como los perfet league R1
- En proceso....

## Notas

- Si Moonani no devuelve pais, el bot muestra `Unknown`. Puedes activar `MOONANI_RESOLVE_COUNTRIES=true` para intentar resolver el pais desde las coordenadas usando reverse geocoding.
- El endpoint publico de Nominatim puede devolver `429 Too Many Requests` si recibe demasiadas consultas. Para un bot publico, lo ideal es usar un geocoder propio, uno autoalojado o un proveedor con cuota adecuada.

## Licencia
**The Unlicense**

<https://unlicense.org>
