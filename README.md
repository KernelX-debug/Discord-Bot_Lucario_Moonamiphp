# Lucario - Moonani Discord Pokemon Coordinates Bot

Bot de Discord en Python que consulta el endpoint de Moonani PokeList para obtener apariciones de Pokemon, extraer coordenadas y las publica en Discord mediante comandos.

## Que hace este proyecto

- Consulta el endpoint `https://moonani.com/PokeList/ajax.php?page=pokemon&action=load`
- Limpia el HTML que devuelve Moonani en campos como nombre, IV, coordenadas y pais
- Extrae coordenadas listas para copiar y pegar, además de link dirigido a google maps.
- Permite buscar por nombre parcial
- Permite filtrar por IV minimo y por disponibilidad de variocolor
- Responde en Discord con mensajes compactos

## Estructura del proyecto

- `discord_bot.py`: punto de entrada del bot y definicion de comandos
- `moonani_client.py`: cliente HTTP y logica de parseo/filtrado de resultados
- `test_pokelist_limpio.py`: script base limpio usado para validar la idea original
- `.env.example`: ejemplo de variables de entorno
- `requirements.txt`: dependencias del proyecto

## Comandos disponibles

- `/ping`: verifica si el bot esta en linea
- `/pokemon`: muestra resultados con formato enriquecido
- `/coords`: devuelve coordenadas en formato compacto para copiar

## Requisitos

- Python 3.13 recomendado
- Un bot creado en el [Discord Developer Portal](https://discord.com/developers/applications)

## Instalacion

```powershell
py -3.13 -m pip install -r requirements.txt
@"
"@ | Set-Content .env

```

Configura tu token en `.env`:

```env
DISCORD_BOT_TOKEN=pega_aqui_el_token_de_tu_bot
DISCORD_GUILD_ID=pega_aqui_el_id_del_servidor_de_discord
MOONANI_TIMEOUT=20
MOONANI_PAGE_SIZE=100
MOONANI_MAX_SCAN_RECORDS=10000
MOONANI_RESOLVE_COUNTRIES=false
MOONANI_GEOCODER_ENDPOINT=
MOONANI_GEOCODER_USER_AGENT=Lucario Discord Bot/1.0
```

## Ejecucion

```powershell
py -3.13 discord_bot.py
```

## Ejemplos de uso

```text
/pokemon nombre:wiglett cantidad:3 iv_min:100 shiny:false
/coords nombre:pikachu cantidad:5 iv_min:90 shiny:true
```

## Como invitar el bot a tu servidor

1. Abre tu aplicacion en el [Discord Developer Portal](https://discord.com/developers/applications).
2. Ve a `OAuth2` > `URL Generator`.
3. Marca los scopes `bot` y `applications.commands`.
4. Concede permisos como `View Channels`, `Send Messages`, `Embed Links` y `Read Message History`.
5. Abre el enlace generado y selecciona tu servidor.

## Mejoras futuras

- Agregar busqueda por numero de Pokedex y por rango de CP
- Permitir publicar alertas automaticas en un canal especifico
- Añadir tests unitarios para el parseo del endpoint
- Manejar mejor paises faltantes o banderas invalidas devueltas por Moonani
- Crear paginacion para listas largas dentro de Discord
- Agregar Docker para despliegue sencillo
- Permitir configuracion por servidor usando una base de datos ligera
- Añadir logs estructurados y manejo de reintentos ante errores del endpoint

## Notas

- El parametro `pokemons` del endpoint no filtra de forma fiable por nombre parcial, por eso el filtrado principal se hace del lado del bot.
- El endpoint devuelve fragmentos HTML en varios campos, asi que el cliente limpia esos datos antes de mostrarlos.
- Si Moonani no devuelve pais, el bot muestra `Unknown`. Puedes activar `MOONANI_RESOLVE_COUNTRIES=true` para intentar resolver el pais desde las coordenadas usando reverse geocoding.
- El endpoint publico de Nominatim puede devolver `429 Too Many Requests` si recibe demasiadas consultas. Para un bot publico, lo ideal es usar un geocoder propio, uno autoalojado o un proveedor con cuota adecuada.

## Licencia

