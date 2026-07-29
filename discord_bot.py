import asyncio
import io
import json
import os
import unicodedata
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands
import requests

from moonani_client import MoonaniClient, PokemonSpawn, RocketSpawn
from questtest import search_quests
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

WATCH_KIND_PREFIX = "watch"
GLOBAL_IV100_KIND = "global_iv100"
GLOBAL_IV0_KIND = "global_iv0"
WATCH_SPAWN_COOLDOWN_SECONDS = 90 * 60
WATCH_ERROR_COOLDOWN_SECONDS = 30 * 60
POKEMON_IMAGE_TIMEOUT_SECONDS = 10
POKEMON_IMAGE_MAX_BYTES = 2 * 1024 * 1024

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


def _normalize_watch_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", (value or "").strip().lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


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
        f"Coords: `{spawn.coords}` | Maps: <{spawn.maps_url}>\n"
        f"IV: {spawn.iv_percent}% | CP: {spawn.cp} | Nivel: {spawn.level}\n"
        f"Pais: {spawn.country} | Fin: {spawn.end_time}"
    )


def _build_detail_embed(
    spawn: PokemonSpawn,
    source_label: str,
    thumbnail_attachment_name: Optional[str] = None,
) -> discord.Embed:
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

    if thumbnail_attachment_name:
        embed.set_thumbnail(url=f"attachment://{thumbnail_attachment_name}")
    elif spawn.image_url:
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


def _build_quest_embed(quest: Dict[str, str]) -> discord.Embed:
    embed = discord.Embed(
        title=f"{quest.get('pokemon', 'Quest')} (#{quest.get('pokemon_id', 'N/D')})",
        color=discord.Color.teal(),
    )
    embed.add_field(name="Mision", value=quest.get("quest", "N/D"), inline=False)
    embed.add_field(name="Coords", value=f"`{quest.get('coords', '')}`", inline=False)
    embed.add_field(name="Mapa", value=f"[Abrir en Google Maps]({quest.get('maps', '')})", inline=False)
    embed.add_field(name="Inicio", value=quest.get("inicio", "N/D"), inline=True)
    embed.add_field(name="Fin", value=quest.get("fin", "N/D"), inline=True)
    embed.add_field(name="Pais", value=quest.get("pais", "N/D"), inline=True)
    embed.set_footer(text="Datos obtenidos por Lucario desde Moonani")
    return embed


def _format_coords_line(index: int, spawn: PokemonSpawn) -> str:
    return (
        f"**{index}. {discord.utils.escape_markdown(spawn.name)}** "
        f"(#{spawn.number})\n"
        f"Coords: `{spawn.coords}`\n"
        f"Maps: <{spawn.maps_url}>\n"
        f"IV: {spawn.iv_percent}% | CP: {spawn.cp} | Nivel: {spawn.level}\n"
        f"ATK:{spawn.attack} DEF:{spawn.defense} HP:{spawn.hp}\n"
        f"Inicio: {spawn.start_time or 'N/D'}\n"
        f"Fin: {spawn.end_time or 'N/D'} | Pais: {spawn.country or 'Unknown'}"
    )


async def _run_blocking(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args))


def _pokemon_image_filename(spawn: PokemonSpawn) -> str:
    parsed_path = urlparse(spawn.image_url or "").path
    extension = Path(parsed_path).suffix.lower()
    if extension not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        extension = ".png"
    return f"pokemon_{spawn.number or 'spawn'}{extension}"


def _download_pokemon_image(spawn: PokemonSpawn) -> Optional[Tuple[bytes, str]]:
    if not spawn.image_url:
        return None

    response = requests.get(
        spawn.image_url,
        headers={"User-Agent": "Mozilla/5.0 (Lucario Discord Bot)"},
        timeout=POKEMON_IMAGE_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    content = response.content
    if not content or len(content) > POKEMON_IMAGE_MAX_BYTES:
        return None

    content_type = response.headers.get("Content-Type", "").lower()
    if content_type and "image" not in content_type:
        return None

    return content, _pokemon_image_filename(spawn)


async def _build_pokemon_embed_payload(
    spawn: PokemonSpawn,
    source_label: str,
) -> Tuple[discord.Embed, Optional[discord.File]]:
    image_payload = None
    try:
        image_payload = await _run_blocking(_download_pokemon_image, spawn)
    except Exception:
        image_payload = None

    if image_payload is None:
        return _build_detail_embed(spawn, source_label), None

    image_bytes, filename = image_payload
    embed = _build_detail_embed(spawn, source_label, filename)
    file = discord.File(io.BytesIO(image_bytes), filename=filename)
    return embed, file


async def _send_pokemon_detail_embeds(
    interaction: discord.Interaction,
    results: List[PokemonSpawn],
    source_label: str,
) -> None:
    for spawn in results:
        embed, file = await _build_pokemon_embed_payload(spawn, source_label)
        if file is not None:
            await interaction.followup.send(embed=embed, file=file)
        else:
            await interaction.followup.send(embed=embed)


async def _send_pokemon_embed_to_channel(
    channel: discord.TextChannel,
    spawn: PokemonSpawn,
    source_label: str,
) -> None:
    embed, file = await _build_pokemon_embed_payload(spawn, source_label)
    if file is not None:
        await channel.send(embed=embed, file=file)
    else:
        await channel.send(embed=embed)


class LucarioDiscordBot(commands.Bot):
    def __init__(
        self,
        moonani: MoonaniClient,
        guild_id: Optional[int],
        page_size: int,
        max_scan_records: int,
        settings_path: Path,
        watch_monitor_interval_seconds: int,
        watch_scan_limit: int,
        zero_iv_scan_limit: int,
    ) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.moonani = moonani
        self.guild_id = guild_id
        self.page_size = page_size
        self.max_scan_records = max_scan_records
        self.settings_path = settings_path
        self.watch_monitor_interval_seconds = watch_monitor_interval_seconds
        self.watch_scan_limit = watch_scan_limit
        self.zero_iv_scan_limit = zero_iv_scan_limit
        self.guild_settings = self._load_settings()
        self.watch_seen_cache = {}  # type: Dict[Tuple[int, str], Set[str]]
        self.watch_cooldown_cache = {}  # type: Dict[Tuple[int, str, str], float]
        self.watch_error_cooldown_cache = {}  # type: Dict[int, float]
        self.monitor_task = None  # type: Optional[asyncio.Task]

    def _load_settings(self) -> Dict[str, Dict[str, object]]:
        if not self.settings_path.exists():
            return {}

        try:
            payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        guilds = payload.get("guilds", {})
        if not isinstance(guilds, dict):
            return {}

        normalized = {}  # type: Dict[str, Dict[str, object]]
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

            normalized[str(guild_key)] = {
                "watches": watches,
                "iv100_channels": self._normalize_channel_list(settings.get("iv100_channels", [])),
                "iv0_channels": self._normalize_channel_list(settings.get("iv0_channels", [])),
            }
        return normalized

    def _save_settings(self) -> None:
        self.settings_path.write_text(json.dumps({"guilds": self.guild_settings}, indent=2), encoding="utf-8")

    def _normalize_channel_list(self, raw_channels: object) -> List[int]:
        channels = []
        if not isinstance(raw_channels, list):
            return channels

        for channel_id in raw_channels:
            try:
                parsed_channel_id = int(channel_id)
            except (TypeError, ValueError):
                continue
            if parsed_channel_id not in channels:
                channels.append(parsed_channel_id)

        return channels

    def _ensure_guild_settings(self, guild_id: int) -> Dict[str, object]:
        guild_key = str(guild_id)
        if guild_key not in self.guild_settings:
            self.guild_settings[guild_key] = {
                "watches": [],
                "iv100_channels": [],
                "iv0_channels": [],
            }
        self.guild_settings[guild_key].setdefault("watches", [])
        self.guild_settings[guild_key].setdefault("iv100_channels", [])
        self.guild_settings[guild_key].setdefault("iv0_channels", [])
        return self.guild_settings[guild_key]

    def get_watches(self, guild_id: int) -> List[Dict[str, object]]:
        settings = self._ensure_guild_settings(guild_id)
        return list(settings.get("watches", []))

    def get_global_channels(self, guild_id: int, channel_key: str) -> List[int]:
        settings = self._ensure_guild_settings(guild_id)
        return self._normalize_channel_list(settings.get(channel_key, []))

    def add_global_channel(self, guild_id: int, channel_key: str, channel_id: int) -> bool:
        settings = self._ensure_guild_settings(guild_id)
        channels = self._normalize_channel_list(settings.get(channel_key, []))
        if channel_id in channels:
            return False

        channels.append(channel_id)
        settings[channel_key] = channels
        self.watch_seen_cache.pop((guild_id, channel_key), None)
        self._save_settings()
        return True

    def remove_global_channel(self, guild_id: int, channel_key: str, channel_id: int) -> bool:
        settings = self._ensure_guild_settings(guild_id)
        channels = self._normalize_channel_list(settings.get(channel_key, []))
        if channel_id not in channels:
            return False

        settings[channel_key] = [saved_channel_id for saved_channel_id in channels if saved_channel_id != channel_id]
        self.watch_seen_cache.pop((guild_id, channel_key), None)
        self._save_settings()
        return True

    def add_watch(self, guild_id: int, pokemon: str, channel_id: int) -> None:
        settings = self._ensure_guild_settings(guild_id)
        pokemon_key = _normalize_watch_name(pokemon)
        settings["watches"] = [
            w for w in settings.get("watches", [])
            if _normalize_watch_name(str(w.get("pokemon", ""))) != pokemon_key
        ]
        settings["watches"].append({"pokemon": pokemon.strip(), "channel_id": channel_id})
        self.watch_seen_cache.pop((guild_id, f"{WATCH_KIND_PREFIX}:{pokemon_key}"), None)
        self._save_settings()

    def remove_watch(self, guild_id: int, pokemon: str) -> bool:
        settings = self._ensure_guild_settings(guild_id)
        pokemon_key = _normalize_watch_name(pokemon)
        before = len(settings.get("watches", []))
        settings["watches"] = [
            w for w in settings.get("watches", [])
            if _normalize_watch_name(str(w.get("pokemon", ""))) != pokemon_key
        ]
        removed = len(settings["watches"]) < before
        if removed:
            self.watch_seen_cache.pop((guild_id, f"{WATCH_KIND_PREFIX}:{pokemon_key}"), None)
            self._save_settings()
        return removed

    def _collect_watch_names(self) -> List[str]:
        names = set()
        for settings in self.guild_settings.values():
            for watch in settings.get("watches", []):
                pokemon = _normalize_watch_name(str(watch.get("pokemon", "")))
                if pokemon:
                    names.add(pokemon)
        return sorted(names)

    def _collect_alert_channels(self, channel_key: str) -> List[Tuple[int, int]]:
        channels = []
        for guild_key, settings in self.guild_settings.items():
            try:
                guild_id = int(guild_key)
            except ValueError:
                continue
            for channel_id in self._normalize_channel_list(settings.get(channel_key, [])):
                channels.append((guild_id, channel_id))
        return channels

    def _purge_watch_caches(self) -> None:
        now = asyncio.get_running_loop().time()
        expired_spawn_keys = [
            key for key, timestamp in self.watch_cooldown_cache.items()
            if (now - timestamp) > WATCH_SPAWN_COOLDOWN_SECONDS
        ]
        for key in expired_spawn_keys:
            del self.watch_cooldown_cache[key]

        expired_error_keys = [
            key for key, timestamp in self.watch_error_cooldown_cache.items()
            if (now - timestamp) > WATCH_ERROR_COOLDOWN_SECONDS
        ]
        for key in expired_error_keys:
            del self.watch_error_cooldown_cache[key]

    def _is_watch_on_cooldown(self, guild_id: int, channel_id: int, spawn: PokemonSpawn) -> bool:
        key = (guild_id, channel_id, spawn.number, spawn.coords)
        last_sent = self.watch_cooldown_cache.get(key)
        if last_sent is None:
            return False
        return (asyncio.get_running_loop().time() - last_sent) < WATCH_SPAWN_COOLDOWN_SECONDS

    def _mark_watch_cooldown(self, guild_id: int, channel_id: int, spawn: PokemonSpawn) -> None:
        key = (guild_id, channel_id, spawn.number, spawn.coords)
        self.watch_cooldown_cache[key] = asyncio.get_running_loop().time()

    async def _fetch_watch_source_spawns(self) -> List[PokemonSpawn]:
        return await _run_blocking(
            self.moonani.search_pokemon,
            "",
            self.watch_scan_limit,
            100,
            False,
            0,
            self.watch_scan_limit,
            self.watch_scan_limit,
        )

    async def _fetch_zero_iv_source_spawns(self) -> List[PokemonSpawn]:
        return await _run_blocking(
            self.moonani.list_current_zero_iv_spawns,
            self.zero_iv_scan_limit,
            self.page_size,
            self.max_scan_records,
        )

    async def _resolve_text_channel(self, channel_id: int) -> Optional[discord.TextChannel]:
        channel = self.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            return channel

        try:
            fetched_channel = await self.fetch_channel(channel_id)
        except Exception:
            return None

        if isinstance(fetched_channel, discord.TextChannel):
            return fetched_channel
        return None

    async def _notify_watch_error(self, channel_id: int, exc: Exception, label: str = "seguimientos") -> None:
        now = asyncio.get_running_loop().time()
        if (now - self.watch_error_cooldown_cache.get(channel_id, 0.0)) < WATCH_ERROR_COOLDOWN_SECONDS:
            return

        channel = await self._resolve_text_channel(channel_id)
        if channel is None:
            return

        try:
            await channel.send(
                f"No pude revisar {label} en este momento.\n"
                f"Motivo: {_format_moonani_error(exc)}"
            )
        except Exception:
            return

        self.watch_error_cooldown_cache[channel_id] = now

    async def _send_spawn_alerts(
        self,
        guild_id: int,
        channel_id: int,
        cache_kind: str,
        spawns: List[PokemonSpawn],
    ) -> None:
        channel = await self._resolve_text_channel(channel_id)
        if channel is None:
            return

        seen_key = (guild_id, cache_kind)
        seen = self.watch_seen_cache.setdefault(seen_key, set())

        for spawn in spawns:
            if spawn.unique_key in seen:
                continue
            if self._is_watch_on_cooldown(guild_id, channel_id, spawn):
                seen.add(spawn.unique_key)
                continue

            try:
                await _send_pokemon_embed_to_channel(channel, spawn, "Moonani")
            except Exception as exc:
                print(f"No pude enviar alerta '{cache_kind}' al canal {channel_id}: {exc}")
                break

            seen.add(spawn.unique_key)
            self._mark_watch_cooldown(guild_id, channel_id, spawn)

        self.watch_seen_cache[seen_key] = {spawn.unique_key for spawn in spawns}

    async def _monitor_watch_loop(self) -> None:
        await self.wait_until_ready()
        await asyncio.sleep(self.watch_monitor_interval_seconds)

        while not self.is_closed():
            watch_names = self._collect_watch_names()
            iv100_channels = self._collect_alert_channels("iv100_channels")
            iv0_channels = self._collect_alert_channels("iv0_channels")

            if not watch_names and not iv100_channels and not iv0_channels:
                await asyncio.sleep(self.watch_monitor_interval_seconds)
                continue

            self._purge_watch_caches()

            current_spawns = []  # type: List[PokemonSpawn]
            if watch_names or iv100_channels:
                try:
                    current_spawns = await self._fetch_watch_source_spawns()
                except Exception as exc:
                    notified_channels = set()
                    for settings in self.guild_settings.values():
                        for watch in settings.get("watches", []):
                            channel_id = int(watch.get("channel_id", 0))
                            if channel_id and channel_id not in notified_channels:
                                await self._notify_watch_error(channel_id, exc, "seguimientos de 100 IV")
                                notified_channels.add(channel_id)
                    for _, channel_id in iv100_channels:
                        if channel_id not in notified_channels:
                            await self._notify_watch_error(channel_id, exc, "canales globales IV100")
                            notified_channels.add(channel_id)
                    await asyncio.sleep(self.watch_monitor_interval_seconds)
                    continue

            current_zero_iv_spawns = []  # type: List[PokemonSpawn]
            if iv0_channels:
                try:
                    current_zero_iv_spawns = await self._fetch_zero_iv_source_spawns()
                except Exception as exc:
                    notified_channels = set()
                    for _, channel_id in iv0_channels:
                        if channel_id not in notified_channels:
                            await self._notify_watch_error(channel_id, exc, "canales globales IV0")
                            notified_channels.add(channel_id)
                    await asyncio.sleep(self.watch_monitor_interval_seconds)
                    continue

            for guild_id, channel_id in iv100_channels:
                await self._send_spawn_alerts(
                    guild_id,
                    channel_id,
                    f"{GLOBAL_IV100_KIND}:{channel_id}",
                    current_spawns,
                )

            for guild_id, channel_id in iv0_channels:
                await self._send_spawn_alerts(
                    guild_id,
                    channel_id,
                    f"{GLOBAL_IV0_KIND}:{channel_id}",
                    current_zero_iv_spawns,
                )

            normalized_matches = {}  # type: Dict[str, List[PokemonSpawn]]
            for watch_name in watch_names:
                normalized_matches[watch_name] = []

            for spawn in current_spawns:
                normalized_name = _normalize_watch_name(spawn.name)
                for watch_name in watch_names:
                    if watch_name and watch_name in normalized_name:
                        normalized_matches[watch_name].append(spawn)

            for guild_key, settings in list(self.guild_settings.items()):
                try:
                    guild_id = int(guild_key)
                except ValueError:
                    continue

                for watch in settings.get("watches", []):
                    pokemon_name = str(watch.get("pokemon", "")).strip()
                    channel_id = int(watch.get("channel_id", 0))
                    if not pokemon_name or not channel_id:
                        continue

                    channel = await self._resolve_text_channel(channel_id)
                    if channel is None:
                        continue

                    pokemon_key = _normalize_watch_name(pokemon_name)
                    seen_key = (guild_id, f"{WATCH_KIND_PREFIX}:{pokemon_key}")
                    seen = self.watch_seen_cache.setdefault(seen_key, set())
                    watch_spawns = normalized_matches.get(pokemon_key, [])

                    for spawn in watch_spawns:
                        if spawn.unique_key in seen:
                            continue
                        if self._is_watch_on_cooldown(guild_id, channel_id, spawn):
                            seen.add(spawn.unique_key)
                            continue
                        try:
                            await _send_pokemon_embed_to_channel(channel, spawn, "Moonani")
                        except Exception as exc:
                            print(f"No pude enviar alerta de seguimiento '{pokemon_name}' al canal {channel_id}: {exc}")
                            break
                        seen.add(spawn.unique_key)
                        self._mark_watch_cooldown(guild_id, channel_id, spawn)

                    self.watch_seen_cache[seen_key] = {spawn.unique_key for spawn in watch_spawns}

            await asyncio.sleep(self.watch_monitor_interval_seconds)

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

        self.monitor_task = asyncio.create_task(self._monitor_watch_loop())


def register_commands(bot: LucarioDiscordBot) -> None:
    @bot.tree.command(name="ping", description="Comprueba si el bot esta en linea.")
    async def ping(interaction: discord.Interaction) -> None:
        latency_ms = round(bot.latency * 1000, 2)
        await interaction.response.send_message(f"Pong. Latencia aproximada: {latency_ms} ms")

    @bot.tree.command(name="pokemon", description="Busca Pokemon 100 IV en Moonani.")
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
            await interaction.followup.send("No encontre Pokemon 100 IV con esos filtros.")
            return

        await _send_pokemon_detail_embeds(interaction, results, "Moonani")

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

        lines = [_format_coords_line(index, spawn) for index, spawn in enumerate(results, start=1)]
        chunks = _chunk_lines(lines)
        for chunk_index, chunk in enumerate(chunks, start=1):
            header = f"Bloque {chunk_index}/{len(chunks)}\n\n" if len(lines) > 1 else ""
            await interaction.followup.send(f"{header}{chunk}")

    @bot.tree.command(name="pokemon0", description="Busca Pokemon 0 IV en Moonani.")
    @app_commands.describe(nombre="Nombre completo o parcial del Pokemon", cantidad="Cuantos resultados mostrar (1-10)")
    async def pokemon0(interaction: discord.Interaction, nombre: Optional[str] = None, cantidad: int = 5) -> None:
        if not 1 <= cantidad <= 10:
            await interaction.response.send_message("`cantidad` debe estar entre 1 y 10.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        try:
            results = await _run_blocking(
                bot.moonani.search_zero_iv_pokemon,
                nombre or "",
                cantidad,
                bot.page_size,
                bot.max_scan_records,
            )
        except Exception as exc:
            await interaction.followup.send(f"No pude consultar Moonani IV0 en este momento: {_format_moonani_error(exc)}")
            return

        if not results:
            await interaction.followup.send("No encontre Pokemon 0 IV con esos filtros.")
            return

        await _send_pokemon_detail_embeds(interaction, results, "Moonani")

    @bot.tree.command(name="coords0", description="Devuelve coordenadas de 0 IV listas para copiar.")
    @app_commands.describe(nombre="Nombre completo o parcial del Pokemon", cantidad="Cuantos resultados mostrar (1-15)")
    async def coords0(interaction: discord.Interaction, nombre: Optional[str] = None, cantidad: int = 5) -> None:
        if not 1 <= cantidad <= 15:
            await interaction.response.send_message("`cantidad` debe estar entre 1 y 15.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        try:
            results = await _run_blocking(
                bot.moonani.search_zero_iv_pokemon,
                nombre or "",
                cantidad,
                bot.page_size,
                bot.max_scan_records,
            )
        except Exception as exc:
            await interaction.followup.send(f"No pude consultar Moonani IV0 en este momento: {_format_moonani_error(exc)}")
            return

        if not results:
            await interaction.followup.send("No encontre coordenadas 0 IV con esos filtros.")
            return

        lines = [_format_coords_line(index, spawn) for index, spawn in enumerate(results, start=1)]
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

        await interaction.response.defer(ephemeral=True, thinking=True)
        bot.add_watch(interaction.guild_id, pokemon, canal.id)
        channel_notice_sent = False
        try:
            await canal.send(
                f"Lucario activo el seguimiento de **{pokemon}** en este canal.\n"
                "Revisare Moonani periodicamente y avisare aqui cuando encuentre 100 IV que coincidan."
            )
            channel_notice_sent = True
        except Exception as exc:
            print(f"No pude publicar la activacion del seguimiento '{pokemon}' en el canal {canal.id}: {exc}")
        await interaction.followup.send(
            (
                f"Seguimiento guardado para **{pokemon}** en {canal.mention}.\n"
                "El monitoreo 100 IV quedo activo con una consulta compartida y periodica."
            )
            if channel_notice_sent
            else (
                f"Seguimiento guardado para **{pokemon}** en {canal.mention}, "
                "pero no pude publicar el aviso inicial en ese canal. Revisa permisos de envio."
            ),
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

        embed.set_footer(text="Seguimientos 100 IV activos en Lucario")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="ver_canales_iv", description="Muestra canales globales IV100 e IV0 guardados.")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def ver_canales_iv(interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("Este comando solo se puede usar dentro de un servidor.", ephemeral=True)
            return

        iv100_channels = bot.get_global_channels(interaction.guild_id, "iv100_channels")
        iv0_channels = bot.get_global_channels(interaction.guild_id, "iv0_channels")
        embed = discord.Embed(title="Canales globales IV", color=discord.Color.green())
        embed.add_field(
            name="IV100",
            value="\n".join(f"<#{channel_id}>" for channel_id in iv100_channels) if iv100_channels else "Ninguno",
            inline=False,
        )
        embed.add_field(
            name="IV0",
            value="\n".join(f"<#{channel_id}>" for channel_id in iv0_channels) if iv0_channels else "Ninguno",
            inline=False,
        )
        embed.set_footer(text="Canales globales de alertas salvajes")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="agregar_canal_iv100", description="Activa avisos de todos los Pokemon salvajes IV100 en un canal.")
    @app_commands.describe(canal="Canal donde se enviaran todos los IV100")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def agregar_canal_iv100(interaction: discord.Interaction, canal: discord.TextChannel) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("Este comando solo se puede usar dentro de un servidor.", ephemeral=True)
            return

        added = bot.add_global_channel(interaction.guild_id, "iv100_channels", canal.id)
        if added:
            await interaction.response.send_message(
                f"Canal IV100 agregado: {canal.mention}. Enviare ahi todos los spawns salvajes IV100 nuevos.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"{canal.mention} ya estaba configurado como canal IV100.",
                ephemeral=True,
            )

    @bot.tree.command(name="quitar_canal_iv100", description="Desactiva avisos globales IV100 en un canal.")
    @app_commands.describe(canal="Canal que dejara de recibir todos los IV100")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def quitar_canal_iv100(interaction: discord.Interaction, canal: discord.TextChannel) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("Este comando solo se puede usar dentro de un servidor.", ephemeral=True)
            return

        removed = bot.remove_global_channel(interaction.guild_id, "iv100_channels", canal.id)
        if removed:
            await interaction.response.send_message(f"Canal IV100 quitado: {canal.mention}.", ephemeral=True)
        else:
            await interaction.response.send_message(f"{canal.mention} no estaba configurado como canal IV100.", ephemeral=True)

    @bot.tree.command(name="agregar_canal_iv0", description="Activa avisos de todos los Pokemon salvajes IV0 en un canal.")
    @app_commands.describe(canal="Canal donde se enviaran todos los IV0")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def agregar_canal_iv0(interaction: discord.Interaction, canal: discord.TextChannel) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("Este comando solo se puede usar dentro de un servidor.", ephemeral=True)
            return

        added = bot.add_global_channel(interaction.guild_id, "iv0_channels", canal.id)
        if added:
            await interaction.response.send_message(
                f"Canal IV0 agregado: {canal.mention}. Enviare ahi todos los spawns salvajes IV0 nuevos.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"{canal.mention} ya estaba configurado como canal IV0.",
                ephemeral=True,
            )

    @bot.tree.command(name="quitar_canal_iv0", description="Desactiva avisos globales IV0 en un canal.")
    @app_commands.describe(canal="Canal que dejara de recibir todos los IV0")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def quitar_canal_iv0(interaction: discord.Interaction, canal: discord.TextChannel) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("Este comando solo se puede usar dentro de un servidor.", ephemeral=True)
            return

        removed = bot.remove_global_channel(interaction.guild_id, "iv0_channels", canal.id)
        if removed:
            await interaction.response.send_message(f"Canal IV0 quitado: {canal.mention}.", ephemeral=True)
        else:
            await interaction.response.send_message(f"{canal.mention} no estaba configurado como canal IV0.", ephemeral=True)

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

    @bot.tree.command(name="quest", description="Busca quests por recompensa Pokemon en Moonani.")
    @app_commands.describe(nombre="Nombre del Pokemon de recompensa", cantidad="Cuantos resultados mostrar (1-10)")
    async def quest(interaction: discord.Interaction, nombre: str, cantidad: int = 5) -> None:
        if not 1 <= cantidad <= 10:
            await interaction.response.send_message("`cantidad` debe estar entre 1 y 10.", ephemeral=True)
            return

        nombre = nombre.strip()
        if not nombre:
            await interaction.response.send_message("Debes indicar el nombre del Pokemon.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        try:
            quests = await _run_blocking(search_quests, nombre, cantidad, bot.moonani.timeout)
        except Exception as exc:
            await interaction.followup.send(f"No pude consultar quests en Moonani: {_format_moonani_error(exc)}")
            return

        if not quests:
            await interaction.followup.send(f"No se encontraron resultados para **{nombre}**.")
            return

        for quest_item in quests:
            await interaction.followup.send(embed=_build_quest_embed(quest_item))

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
    watch_monitor_interval_seconds = _read_int_env("LUCARIO_MONITOR_INTERVAL_SECONDS", 180)
    watch_scan_limit = _read_int_env("LUCARIO_ALERT_LIMIT_100IV", 250)
    zero_iv_scan_limit = _read_int_env("LUCARIO_ALERT_LIMIT_0IV", 250)

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
        watch_monitor_interval_seconds=watch_monitor_interval_seconds,
        watch_scan_limit=watch_scan_limit,
        zero_iv_scan_limit=zero_iv_scan_limit,
    )
    register_commands(bot)
    bot.run(token)


if __name__ == "__main__":
    main()
