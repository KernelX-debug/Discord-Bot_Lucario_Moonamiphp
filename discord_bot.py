import asyncio
import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import discord
from discord import app_commands
from discord.ext import commands
import requests

from moonani_client import MoonaniClient, PokemonSpawn, RocketSpawn
from raidtest import get_raid_data

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


ROCKET_EMOJIS = {
    "arlo": "🔴",
    "cliff": "🟠",
    "sierra": "🟣",
    "giovanni": "👑",
    "fire": "🔥",
    "ice": "❄️",
    "grass": "🌿",
    "electric": "⚡",
    "water": "💧",
    "dark": "🌑",
    "psychic": "🔮",
    "flying": "🦅",
    "ground": "🟫",
    "metal": "⚙️",
    "ghost": "👻",
    "bug": "🐛",
    "fighting": "🥊",
    "poison": "☠️",
    "dragon": "🐉",
    "rock": "🪨",
    "fairy": "🧚",
    "normal": "⭐",
    "grunt": "👤",
}

ROCKET_CHOICES = [
    app_commands.Choice(name="Todos", value=""),
    app_commands.Choice(name="Giovanni", value="giovanni"),
    app_commands.Choice(name="Arlo", value="arlo"),
    app_commands.Choice(name="Cliff", value="cliff"),
    app_commands.Choice(name="Sierra", value="sierra"),
    app_commands.Choice(name="Fire", value="fire"),
    app_commands.Choice(name="Ice", value="ice"),
    app_commands.Choice(name="Grass", value="grass"),
    app_commands.Choice(name="Electric", value="electric"),
    app_commands.Choice(name="Water", value="water"),
    app_commands.Choice(name="Dark", value="dark"),
    app_commands.Choice(name="Psychic", value="psychic"),
    app_commands.Choice(name="Flying", value="flying"),
    app_commands.Choice(name="Ground", value="ground"),
    app_commands.Choice(name="Metal", value="metal"),
    app_commands.Choice(name="Ghost", value="ghost"),
    app_commands.Choice(name="Bug", value="bug"),
    app_commands.Choice(name="Fighting", value="fighting"),
    app_commands.Choice(name="Poison", value="poison"),
    app_commands.Choice(name="Dragon", value="dragon"),
    app_commands.Choice(name="Rock", value="rock"),
    app_commands.Choice(name="Fairy", value="fairy"),
    app_commands.Choice(name="Normal", value="normal"),
    app_commands.Choice(name="Grunt", value="grunt"),
]


def _read_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default

    try:
        return int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"La variable {name} debe ser un numero entero.") from exc


def _read_bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _format_moonani_error(exc: Exception) -> str:
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        if exc.response.status_code == 403:
            return (
                "Moonani devolvio `403 Forbidden` desde este entorno. "
                "Eso suele indicar bloqueo de Cloudflare o restriccion del host donde corre el bot."
            )
        return f"Moonani devolvio HTTP {exc.response.status_code}."
    return f"{type(exc).__name__}: {exc}"


def _chunk_lines(lines: Iterable[str], max_chars: int = 1800) -> List[str]:
    chunks = []  # type: List[str]
    current = ""

    for line in lines:
        candidate = f"{current}\n\n{line}" if current else line
        if len(candidate) > max_chars:
            if current:
                chunks.append(current)
            current = line
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks


def _format_spawn_short(index: int, spawn: PokemonSpawn) -> str:
    return (
        f"**{index}. {discord.utils.escape_markdown(spawn.name)}** "
        f"(#{spawn.number})\n"
        f"Coords: `{spawn.coords}` | [Maps]({spawn.maps_url})\n"
        f"IV: {spawn.iv_percent}% | CP: {spawn.cp} | Nivel: {spawn.level}\n"
        f"Pais: {spawn.country} | Fin: {spawn.end_time}"
    )


def _build_detail_embed(spawn: PokemonSpawn, source_label: str) -> discord.Embed:
    if spawn.iv_percent == 100:
        color = discord.Color.gold()
    elif spawn.iv_percent == 0:
        color = discord.Color.red()
    else:
        color = discord.Color.blurple()

    embed = discord.Embed(
        title=f"{spawn.name} (#{spawn.number})",
        description=f"Coords: `{spawn.coords}`",
        color=color,
    )
    embed.add_field(name="Mapa", value=f"[Abrir en Google Maps]({spawn.maps_url})", inline=False)
    embed.add_field(name="IV", value=f"{spawn.iv_percent}%", inline=True)
    embed.add_field(name="CP", value=str(spawn.cp), inline=True)
    embed.add_field(name="Nivel", value=str(spawn.level), inline=True)
    embed.add_field(
        name="Stats",
        value=f"ATK {spawn.attack} | DEF {spawn.defense} | HP {spawn.hp}",
        inline=False,
    )
    embed.add_field(name="Inicio", value=spawn.start_time or "N/D", inline=True)
    embed.add_field(name="Fin", value=spawn.end_time or "N/D", inline=True)
    embed.add_field(name="Pais", value=spawn.country or "Unknown", inline=True)
    embed.set_footer(text=f"Datos obtenidos por Lucario desde {source_label}")

    if spawn.image_url:
        embed.set_thumbnail(url=spawn.image_url)

    return embed


def _build_list_embed(results: List[PokemonSpawn], query: str, source_label: str) -> discord.Embed:
    title = f"Resultados de {source_label}"
    if query:
        title = f'Resultados para "{query}" en {source_label}'

    embed = discord.Embed(
        title=title,
        description="\n\n".join(_format_spawn_short(index, spawn) for index, spawn in enumerate(results, start=1)),
        color=discord.Color.blurple(),
    )
    embed.set_footer(text=f"Datos obtenidos por Lucario desde {source_label}")
    return embed


def _build_rocket_embed(rocket: RocketSpawn) -> discord.Embed:
    emoji = ROCKET_EMOJIS.get(rocket.rocket_type.lower(), "🚀")
    color = discord.Color.from_rgb(30, 0, 60) if rocket.is_leader else discord.Color.dark_red()
    title = f"{emoji} Lider {rocket.display_name}" if rocket.is_leader else f"{emoji} Rocket: {rocket.display_name}"

    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="Coords", value=f"`{rocket.coords}`", inline=False)
    embed.add_field(name="Mapa", value=f"[Abrir en Google Maps]({rocket.maps_url})", inline=False)
    embed.add_field(name="Inicio", value=rocket.start_time, inline=True)
    embed.add_field(name="Fin", value=rocket.end_time, inline=True)
    embed.add_field(name="Pais", value=rocket.country.upper() if rocket.country else "??", inline=True)
    embed.set_footer(text="Datos obtenidos por Lucario desde Moonani")
    return embed


def _build_raid_embed(raid: Dict[str, str]) -> discord.Embed:
    embed = discord.Embed(
        title=raid.get("raid_name", "Raid"),
        color=discord.Color.orange(),
    )
    embed.add_field(name="Nivel", value=raid.get("level", "N/D"), inline=True)
    embed.add_field(name="Pais", value=raid.get("country", "N/D"), inline=True)
    embed.add_field(name="Coords", value=f"`{raid.get('coords', '')}`", inline=False)
    embed.add_field(name="Mapa", value=f"[Abrir en Google Maps]({raid.get('maps_url', '')})", inline=False)
    embed.set_footer(text="Datos obtenidos por Lucario desde Moonani")
    return embed


async def _run_blocking(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args))


class LucarioDiscordBot(commands.Bot):
    def __init__(
        self,
        moonani: MoonaniClient,
        guild_id: Optional[int],
        page_size: int,
        max_scan_records: int,
        settings_path: Path,
    ) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.moonani = moonani
        self.guild_id = guild_id
        self.page_size = page_size
        self.max_scan_records = max_scan_records
        self.settings_path = settings_path
        self.guild_settings = self._load_settings()

    def _load_settings(self) -> Dict[str, Dict[str, List[Dict[str, object]]]]:
        if not self.settings_path.exists():
            return {}

        try:
            payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        guilds = payload.get("guilds", {})
        if not isinstance(guilds, dict):
            return {}

        normalized = {}  # type: Dict[str, Dict[str, List[Dict[str, object]]]]
        for guild_key, settings in guilds.items():
            if not isinstance(settings, dict):
                continue
            raw_watches = settings.get("watches", [])
            watches = []
            if isinstance(raw_watches, list):
                for watch in raw_watches:
                    if isinstance(watch, dict) and watch.get("pokemon") and watch.get("channel_id"):
                        watches.append(
                            {
                                "pokemon": str(watch["pokemon"]),
                                "channel_id": int(watch["channel_id"]),
                            }
                        )
            normalized[str(guild_key)] = {"watches": watches}
        return normalized

    def _save_settings(self) -> None:
        self.settings_path.write_text(json.dumps({"guilds": self.guild_settings}, indent=2), encoding="utf-8")

    def _ensure_guild_settings(self, guild_id: int) -> Dict[str, List[Dict[str, object]]]:
        guild_key = str(guild_id)
        if guild_key not in self.guild_settings:
            self.guild_settings[guild_key] = {"watches": []}
        self.guild_settings[guild_key].setdefault("watches", [])
        return self.guild_settings[guild_key]

    def get_watches(self, guild_id: int) -> List[Dict[str, object]]:
        settings = self._ensure_guild_settings(guild_id)
        return list(settings.get("watches", []))

    def add_watch(self, guild_id: int, pokemon: str, channel_id: int) -> None:
        settings = self._ensure_guild_settings(guild_id)
        pokemon_key = pokemon.lower().strip()
        settings["watches"] = [
            w for w in settings.get("watches", [])
            if str(w.get("pokemon", "")).lower() != pokemon_key
        ]
        settings["watches"].append({"pokemon": pokemon.strip(), "channel_id": channel_id})
        self._save_settings()

    def remove_watch(self, guild_id: int, pokemon: str) -> bool:
        settings = self._ensure_guild_settings(guild_id)
        pokemon_key = pokemon.lower().strip()
        before = len(settings.get("watches", []))
        settings["watches"] = [
            w for w in settings.get("watches", [])
            if str(w.get("pokemon", "")).lower() != pokemon_key
        ]
        removed = len(settings["watches"]) < before
        if removed:
            self._save_settings()
        return removed

    async def setup_hook(self) -> None:
        if self.guild_id:
            guild = discord.Object(id=self.guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            print(f"Comandos slash sincronizados en el servidor {self.guild_id}: {len(synced)}")
            self.tree.clear_commands(guild=None)
            cleared = await self.tree.sync()
            print(f"Comandos slash globales eliminados para evitar duplicados: {len(cleared)}")
        else:
            synced = await self.tree.sync()
            print(f"Comandos slash globales sincronizados: {len(synced)}")


def register_commands(bot: LucarioDiscordBot) -> None:
    @bot.tree.command(name="ping", description="Comprueba si el bot esta en linea.")
    async def ping(interaction: discord.Interaction) -> None:
        latency_ms = round(bot.latency * 1000, 2)
        await interaction.response.send_message(f"Pong. Latencia aproximada: {latency_ms} ms")

    @bot.tree.command(name="pokemon", description="Busca pokemones 100 IV en Moonani y devuelve sus coordenadas.")
    @app_commands.describe(nombre="Nombre completo o parcial del Pokemon", cantidad="Cuantos resultados mostrar (1-10)")
    async def pokemon(interaction: discord.Interaction, nombre: Optional[str] = None, cantidad: int = 5) -> None:
        if not 1 <= cantidad <= 10:
            await interaction.response.send_message("`cantidad` debe estar entre 1 y 10.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        try:
            results = await _run_blocking(
                bot.moonani.search_pokemon,
                nombre or "",
                cantidad,
                100,
                False,
                0,
                bot.page_size,
                bot.max_scan_records,
            )
        except Exception as exc:
            await interaction.followup.send(f"No pude consultar Moonani en este momento: {_format_moonani_error(exc)}")
            return

        if not results:
            await interaction.followup.send("No encontre pokemones que coincidan con esos filtros.")
            return
        if len(results) == 1:
            await interaction.followup.send(embed=_build_detail_embed(results[0], "Moonani"))
            return
        await interaction.followup.send(embed=_build_list_embed(results, nombre or "", "Moonani"))

    @bot.tree.command(name="coords", description="Devuelve coordenadas de 100 IV listas para copiar.")
    @app_commands.describe(nombre="Nombre completo o parcial del Pokemon", cantidad="Cuantos resultados mostrar (1-15)")
    async def coords(interaction: discord.Interaction, nombre: Optional[str] = None, cantidad: int = 5) -> None:
        if not 1 <= cantidad <= 15:
            await interaction.response.send_message("`cantidad` debe estar entre 1 y 15.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        try:
            results = await _run_blocking(
                bot.moonani.search_pokemon,
                nombre or "",
                cantidad,
                100,
                False,
                0,
                bot.page_size,
                bot.max_scan_records,
            )
        except Exception as exc:
            await interaction.followup.send(f"No pude consultar Moonani en este momento: {_format_moonani_error(exc)}")
            return

        if not results:
            await interaction.followup.send("No encontre coordenadas con esos filtros.")
            return

        lines = []
        for index, spawn in enumerate(results, start=1):
            lines.append(
                f"{index}. {spawn.name} (#{spawn.number})\n"
                f"Coords: `{spawn.coords}`\n"
                f"Maps: {spawn.maps_url}\n"
                f"IV: {spawn.iv_percent}% | CP: {spawn.cp} | Fin: {spawn.end_time}"
            )
        for chunk_index, chunk in enumerate(_chunk_lines(lines), start=1):
            header = f"Bloque {chunk_index}/{len(_chunk_lines(lines))}\n\n" if len(lines) > 1 else ""
            await interaction.followup.send(f"{header}{chunk}")

    @bot.tree.command(name="pokemon0", description="Busca pokemones 0 IV en Moonani y devuelve sus coordenadas.")
    @app_commands.describe(nombre="Nombre completo o parcial del Pokemon", cantidad="Cuantos resultados mostrar (1-10)")
    async def pokemon0(interaction: discord.Interaction, nombre: Optional[str] = None, cantidad: int = 5) -> None:
        if not 1 <= cantidad <= 10:
            await interaction.response.send_message("`cantidad` debe estar entre 1 y 10.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        try:
            results = await _run_blocking(bot.moonani.search_zero_iv_pokemon, nombre or "", cantidad)
        except Exception as exc:
            await interaction.followup.send(f"No pude consultar Moonani IV0 en este momento: {_format_moonani_error(exc)}")
            return

        if not results:
            await interaction.followup.send("No encontre pokemones 0 IV que coincidan con esos filtros.")
            return
        if len(results) == 1:
            await interaction.followup.send(embed=_build_detail_embed(results[0], "Moonani IV0"))
            return
        await interaction.followup.send(embed=_build_list_embed(results, nombre or "", "Moonani IV0"))

    @bot.tree.command(name="coords0", description="Devuelve coordenadas de 0 IV listas para copiar.")
    @app_commands.describe(nombre="Nombre completo o parcial del Pokemon", cantidad="Cuantos resultados mostrar (1-15)")
    async def coords0(interaction: discord.Interaction, nombre: Optional[str] = None, cantidad: int = 5) -> None:
        if not 1 <= cantidad <= 15:
            await interaction.response.send_message("`cantidad` debe estar entre 1 y 15.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        try:
            results = await _run_blocking(bot.moonani.search_zero_iv_pokemon, nombre or "", cantidad)
        except Exception as exc:
            await interaction.followup.send(f"No pude consultar Moonani IV0 en este momento: {_format_moonani_error(exc)}")
            return

        if not results:
            await interaction.followup.send("No encontre coordenadas 0 IV con esos filtros.")
            return

        lines = []
        for index, spawn in enumerate(results, start=1):
            lines.append(
                f"{index}. {spawn.name} (#{spawn.number})\n"
                f"Coords: `{spawn.coords}`\n"
                f"Maps: {spawn.maps_url}\n"
                f"IV: {spawn.iv_percent}% | CP: {spawn.cp} | Fin: {spawn.end_time}"
            )
        chunks = _chunk_lines(lines)
        for chunk_index, chunk in enumerate(chunks, start=1):
            header = f"Bloque {chunk_index}/{len(chunks)}\n\n" if len(lines) > 1 else ""
            await interaction.followup.send(f"{header}{chunk}")

    @bot.tree.command(name="agregar_seguimiento", description="Guarda un seguimiento de Pokimon especifico en un canal.")
    @app_commands.describe(pokemon="Nombre del Pokimon a seguir", canal="Canal asociado al seguimiento")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def agregar_seguimiento(
        interaction: discord.Interaction,
        pokemon: str,
        canal: discord.TextChannel,
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("Este comando solo se puede usar dentro de un servidor.", ephemeral=True)
            return

        pokemon = pokemon.strip()
        if not pokemon:
            await interaction.response.send_message("Debes indicar el nombre del Pokimon.", ephemeral=True)
            return

        bot.add_watch(interaction.guild_id, pokemon, canal.id)
        await interaction.response.send_message(
            f"Seguimiento guardado para **{pokemon}** en {canal.mention}.\n"
            "Nota: en este despliegue no hay monitoreo automatico para evitar bloqueos 403 de Moonani.",
            ephemeral=True,
        )

    @bot.tree.command(name="quitar_seguimiento", description="Quita un seguimiento guardado.")
    @app_commands.describe(pokemon="Nombre del Pokimon que ya no quieres seguir")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def quitar_seguimiento(interaction: discord.Interaction, pokemon: str) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("Este comando solo se puede usar dentro de un servidor.", ephemeral=True)
            return

        removed = bot.remove_watch(interaction.guild_id, pokemon.strip())
        if removed:
            await interaction.response.send_message(f"Se quito el seguimiento de **{pokemon}**.", ephemeral=True)
        else:
            await interaction.response.send_message(f"No habia seguimiento configurado para **{pokemon}**.", ephemeral=True)

    @bot.tree.command(name="ver_seguimientos", description="Muestra los seguimientos guardados en este servidor.")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def ver_seguimientos(interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("Este comando solo se puede usar dentro de un servidor.", ephemeral=True)
            return

        watches = bot.get_watches(interaction.guild_id)
        embed = discord.Embed(title="Seguimientos guardados", color=discord.Color.green())

        if not watches:
            embed.description = "No hay seguimientos guardados."
        else:
            lines = []
            for watch in watches:
                lines.append(f"• **{watch['pokemon']}** -> <#{watch['channel_id']}>")
            embed.description = "\n".join(lines)

        embed.set_footer(text="Monitoreo automatico desactivado en este despliegue")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="rocket", description="Busca Rockets en Moonani por tipo o lider.")
    @app_commands.describe(tipo="Tipo o lider Rocket a buscar", cantidad="Cuantos resultados mostrar (1-10)")
    @app_commands.choices(tipo=ROCKET_CHOICES)
    async def rocket(
        interaction: discord.Interaction,
        tipo: Optional[app_commands.Choice[str]] = None,
        cantidad: int = 5,
    ) -> None:
        if not 1 <= cantidad <= 10:
            await interaction.response.send_message("`cantidad` debe estar entre 1 y 10.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        type_filter = tipo.value if tipo else ""

        try:
            results = await _run_blocking(bot.moonani.search_rockets, type_filter, cantidad)
        except Exception as exc:
            await interaction.followup.send(f"No pude consultar Rockets en Moonani: {_format_moonani_error(exc)}")
            return

        if not results:
            label = tipo.name if tipo else "Rockets"
            await interaction.followup.send(f"No encontre **{label}** activos en este momento.")
            return

        if len(results) == 1:
            await interaction.followup.send(embed=_build_rocket_embed(results[0]))
            return

        label = tipo.name if tipo else "Rockets"
        embed = discord.Embed(title=f"{label} — {len(results)} resultado(s)", color=discord.Color.dark_red())
        lines = []
        for index, rocket_item in enumerate(results, start=1):
            emoji = ROCKET_EMOJIS.get(rocket_item.rocket_type.lower(), "🚀")
            lines.append(
                f"**{index}. {emoji} {rocket_item.display_name}**\n"
                f"Coords: `{rocket_item.coords}` | [Maps]({rocket_item.maps_url})\n"
                f"Inicio: {rocket_item.start_time} | Fin: {rocket_item.end_time} | Pais: {rocket_item.country.upper() if rocket_item.country else '??'}"
            )
        embed.description = "\n\n".join(lines)
        embed.set_footer(text="Datos obtenidos por Lucario desde Moonani")
        await interaction.followup.send(embed=embed)

    @bot.tree.command(name="raid", description="Consulta raids en Moonani y devuelve coordenadas.")
    @app_commands.describe(nombre="Filtro opcional por nombre del raid", cantidad="Cuantos resultados mostrar (1-10)")
    async def raid(interaction: discord.Interaction, nombre: Optional[str] = None, cantidad: int = 5) -> None:
        if not 1 <= cantidad <= 10:
            await interaction.response.send_message("`cantidad` debe estar entre 1 y 10.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        try:
            raids = await _run_blocking(get_raid_data)
        except Exception as exc:
            await interaction.followup.send(f"No pude consultar raids en Moonani: {_format_moonani_error(exc)}")
            return

        if nombre:
            name_key = nombre.lower().strip()
            raids = [raid_item for raid_item in raids if name_key in str(raid_item.get("raid_name", "")).lower()]

        raids = raids[:cantidad]
        if not raids:
            await interaction.followup.send("No encontre raids que coincidan con ese filtro.")
            return

        if len(raids) == 1:
            await interaction.followup.send(embed=_build_raid_embed(raids[0]))
            return

        embed = discord.Embed(title="Raids en Moonani", color=discord.Color.orange())
        lines = []
        for index, raid_item in enumerate(raids, start=1):
            lines.append(
                f"**{index}. {raid_item.get('raid_name', 'Raid')}**\n"
                f"Nivel: {raid_item.get('level', 'N/D')} | Pais: {raid_item.get('country', 'N/D')}\n"
                f"Coords: `{raid_item.get('coords', '')}` | [Maps]({raid_item.get('maps_url', '')})"
            )
        embed.description = "\n\n".join(lines)
        embed.set_footer(text="Datos obtenidos por Lucario desde Moonani")
        await interaction.followup.send(embed=embed)

    @bot.tree.error
    async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        message = f"Ocurrio un error al ejecutar el comando: `{type(error).__name__}`"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.NotFound:
            print(f"No pude responder a la interaccion porque ya no existe: {error}")


def main() -> None:
    if load_dotenv is not None:
        load_dotenv()

    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Falta la variable de entorno DISCORD_BOT_TOKEN.")

    guild_id_raw = os.getenv("DISCORD_GUILD_ID", "").strip()
    guild_id = int(guild_id_raw) if guild_id_raw else None

    timeout = _read_int_env("MOONANI_TIMEOUT", 20)
    page_size = _read_int_env("MOONANI_PAGE_SIZE", 100)
    max_scan_records = _read_int_env("MOONANI_MAX_SCAN_RECORDS", 10000)
    resolve_countries = _read_bool_env("MOONANI_RESOLVE_COUNTRIES", False)
    geocoder_endpoint = os.getenv("MOONANI_GEOCODER_ENDPOINT", "").strip()
    geocoder_user_agent = os.getenv("MOONANI_GEOCODER_USER_AGENT", "").strip() or "Lucario Discord Bot/1.0"
    settings_path = Path(os.getenv("LUCARIO_SETTINGS_PATH", "lucario_guild_settings.json")).resolve()

    moonani = MoonaniClient(
        timeout=timeout,
        resolve_missing_countries=resolve_countries,
        geocoder_endpoint=geocoder_endpoint or "https://nominatim.openstreetmap.org/reverse",
        geocoder_user_agent=geocoder_user_agent,
    )
    bot = LucarioDiscordBot(
        moonani=moonani,
        guild_id=guild_id,
        page_size=page_size,
        max_scan_records=max_scan_records,
        settings_path=settings_path,
    )
    register_commands(bot)
    bot.run(token)


if __name__ == "__main__":
    main()
