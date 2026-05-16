import asyncio
import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from moonani_client import MoonaniClient, PokemonSpawn

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


HUNDO_KIND = "100iv"
ZERO_KIND = "0iv"
ALERT_KIND_LABELS = {
    HUNDO_KIND: "100 IV",
    ZERO_KIND: "0 IV",
}


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


def _format_spawn_short(index: int, spawn: PokemonSpawn) -> str:
    return (
        f"**{index}. {discord.utils.escape_markdown(spawn.name)}** "
        f"(#{spawn.number})\n"
        f"Coords: `{spawn.coords}` | [Maps]({spawn.maps_url})\n"
        f"IV: {spawn.iv_percent}% | CP: {spawn.cp} | Nivel: {spawn.level}\n"
        f"Pais: {spawn.country} | Fin: {spawn.end_time}"
    )


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


def _build_detail_embed(spawn: PokemonSpawn, source_label: str = "Moonani") -> discord.Embed:
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


def _build_alert_embed(spawn: PokemonSpawn, alert_kind: str) -> discord.Embed:
    label = ALERT_KIND_LABELS.get(alert_kind, "Spawn")
    source = "Moonani IV0" if alert_kind == ZERO_KIND else "Moonani"
    embed = _build_detail_embed(spawn, source_label=source)
    embed.title = f"Nuevo {label}: {spawn.name} (#{spawn.number})"
    return embed


async def _run_blocking(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args))


async def _search_hundo_spawns(bot: "LucarioDiscordBot", nombre: Optional[str], cantidad: int) -> List[PokemonSpawn]:
    return await _run_blocking(
        bot.moonani.search_pokemon,
        nombre or "",
        cantidad,
        100,
        False,
        0,
        bot.page_size,
        bot.max_scan_records,
    )


async def _search_zero_spawns(bot: "LucarioDiscordBot", nombre: Optional[str], cantidad: int) -> List[PokemonSpawn]:
    return await _run_blocking(
        bot.moonani.search_zero_iv_pokemon,
        nombre or "",
        cantidad,
    )


class LucarioDiscordBot(commands.Bot):
    def __init__(
        self,
        moonani: MoonaniClient,
        guild_id: Optional[int],
        page_size: int,
        max_scan_records: int,
        settings_path: Path,
        monitor_interval_seconds: int,
        alert_limit_hundo: int,
        alert_limit_zero: int,
    ) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.moonani = moonani
        self.guild_id = guild_id
        self.page_size = page_size
        self.max_scan_records = max_scan_records
        self.settings_path = settings_path
        self.monitor_interval_seconds = monitor_interval_seconds
        self.alert_limit_hundo = alert_limit_hundo
        self.alert_limit_zero = alert_limit_zero
        self.guild_settings = self._load_settings()
        self.seen_spawns = {}  # type: Dict[Tuple[int, str], Set[str]]
        self.monitor_task = None  # type: Optional[asyncio.Task]

    def _load_settings(self) -> Dict[str, Dict[str, Optional[int]]]:
        if not self.settings_path.exists():
            return {}

        try:
            payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        if not isinstance(payload, dict):
            return {}

        guilds = payload.get("guilds", {})
        if not isinstance(guilds, dict):
            return {}

        normalized = {}  # type: Dict[str, Dict[str, Optional[int]]]
        for guild_key, settings in guilds.items():
            if not isinstance(settings, dict):
                continue
            normalized[str(guild_key)] = {
                HUNDO_KIND: settings.get(HUNDO_KIND),
                ZERO_KIND: settings.get(ZERO_KIND),
            }
        return normalized

    def _save_settings(self) -> None:
        payload = {"guilds": self.guild_settings}
        self.settings_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _ensure_guild_settings(self, guild_id: int) -> Dict[str, Optional[int]]:
        guild_key = str(guild_id)
        if guild_key not in self.guild_settings:
            self.guild_settings[guild_key] = {
                HUNDO_KIND: None,
                ZERO_KIND: None,
            }
        return self.guild_settings[guild_key]

    def get_channel_id(self, guild_id: int, alert_kind: str) -> Optional[int]:
        settings = self._ensure_guild_settings(guild_id)
        value = settings.get(alert_kind)
        return int(value) if value else None

    def set_channel_id(self, guild_id: int, alert_kind: str, channel_id: int) -> None:
        settings = self._ensure_guild_settings(guild_id)
        settings[alert_kind] = channel_id
        self._save_settings()

    def clear_channel_id(self, guild_id: int, alert_kind: str) -> None:
        settings = self._ensure_guild_settings(guild_id)
        settings[alert_kind] = None
        self._save_settings()

    async def _fetch_current_spawns(self, alert_kind: str) -> List[PokemonSpawn]:
        if alert_kind == HUNDO_KIND:
            return await _run_blocking(
                self.moonani.list_current_hundo_spawns,
                self.alert_limit_hundo,
                self.page_size,
                self.max_scan_records,
            )
        return await _run_blocking(
            self.moonani.list_current_zero_iv_spawns,
            self.alert_limit_zero,
        )

    async def _prime_seen_cache(self, guild_id: int, alert_kind: str) -> None:
        channel_id = self.get_channel_id(guild_id, alert_kind)
        if not channel_id:
            self.seen_spawns[(guild_id, alert_kind)] = set()
            return

        try:
            current_spawns = await self._fetch_current_spawns(alert_kind)
        except Exception as exc:  # pragma: no cover
            print(f"No pude inicializar cache de {alert_kind} para guild {guild_id}: {exc}")
            self.seen_spawns[(guild_id, alert_kind)] = set()
            return

        self.seen_spawns[(guild_id, alert_kind)] = {spawn.unique_key for spawn in current_spawns}

    async def _bootstrap_seen_cache(self) -> None:
        for guild_key in list(self.guild_settings.keys()):
            try:
                guild_id = int(guild_key)
            except ValueError:
                continue

            await self._prime_seen_cache(guild_id, HUNDO_KIND)
            await self._prime_seen_cache(guild_id, ZERO_KIND)

    async def _monitor_alerts_loop(self) -> None:
        await self.wait_until_ready()

        while not self.is_closed():
            for guild_key, settings in list(self.guild_settings.items()):
                try:
                    guild_id = int(guild_key)
                except ValueError:
                    continue

                for alert_kind in (HUNDO_KIND, ZERO_KIND):
                    channel_id = settings.get(alert_kind)
                    if not channel_id:
                        continue

                    channel = self.get_channel(int(channel_id))
                    if channel is None:
                        try:
                            channel = await self.fetch_channel(int(channel_id))
                        except Exception:
                            continue

                    try:
                        current_spawns = await self._fetch_current_spawns(alert_kind)
                    except Exception as exc:  # pragma: no cover
                        print(f"Error monitoreando {alert_kind} para guild {guild_id}: {exc}")
                        continue

                    seen_key = (guild_id, alert_kind)
                    seen = self.seen_spawns.setdefault(seen_key, set())

                    new_spawns = [spawn for spawn in current_spawns if spawn.unique_key not in seen]
                    for spawn in new_spawns:
                        try:
                            await channel.send(embed=_build_alert_embed(spawn, alert_kind))
                        except Exception as exc:  # pragma: no cover
                            print(f"No pude enviar alerta {alert_kind} al canal {channel_id}: {exc}")
                            break
                        seen.add(spawn.unique_key)

                    for spawn in current_spawns:
                        seen.add(spawn.unique_key)

            await asyncio.sleep(self.monitor_interval_seconds)

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

        await self._bootstrap_seen_cache()
        self.monitor_task = asyncio.create_task(self._monitor_alerts_loop())


def register_commands(bot: LucarioDiscordBot) -> None:
    @bot.tree.command(name="ping", description="Comprueba si el bot esta en linea.")
    async def ping(interaction: discord.Interaction) -> None:
        latency_ms = round(bot.latency * 1000, 2)
        await interaction.response.send_message(f"Pong. Latencia aproximada: {latency_ms} ms")

    @bot.tree.command(name="pokemon", description="Busca pokemones 100 IV en Moonani y devuelve sus coordenadas.")
    @app_commands.describe(
        nombre="Nombre completo o parcial del Pokemon",
        cantidad="Cuantos resultados mostrar (1-10)",
    )
    async def pokemon(
        interaction: discord.Interaction,
        nombre: Optional[str] = None,
        cantidad: int = 5,
    ) -> None:
        if not 1 <= cantidad <= 10:
            await interaction.response.send_message("`cantidad` debe estar entre 1 y 10.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        try:
            results = await _search_hundo_spawns(bot, nombre, cantidad)
        except Exception as exc:  # pragma: no cover
            await interaction.followup.send(f"No pude consultar Moonani en este momento: `{type(exc).__name__}: {exc}`")
            return

        if not results:
            await interaction.followup.send("No encontre pokemones que coincidan con esos filtros.")
            return

        if len(results) == 1:
            await interaction.followup.send(embed=_build_detail_embed(results[0], source_label="Moonani"))
            return

        await interaction.followup.send(embed=_build_list_embed(results, query=nombre or "", source_label="Moonani"))

    @bot.tree.command(name="coords", description="Devuelve coordenadas de 100 IV listas para copiar.")
    @app_commands.describe(
        nombre="Nombre completo o parcial del Pokemon",
        cantidad="Cuantos resultados mostrar (1-15)",
    )
    async def coords(
        interaction: discord.Interaction,
        nombre: Optional[str] = None,
        cantidad: int = 5,
    ) -> None:
        if not 1 <= cantidad <= 15:
            await interaction.response.send_message("`cantidad` debe estar entre 1 y 15.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        try:
            results = await _search_hundo_spawns(bot, nombre, cantidad)
        except Exception as exc:  # pragma: no cover
            await interaction.followup.send(f"No pude consultar Moonani en este momento: `{type(exc).__name__}: {exc}`")
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

        chunks = _chunk_lines(lines)
        for chunk_index, chunk in enumerate(chunks, start=1):
            header = ""
            if len(lines) > 1:
                header = f"Bloque {chunk_index}/{len(chunks)}\n\n"
            await interaction.followup.send(f"{header}{chunk}")

    @bot.tree.command(name="pokemon0", description="Busca pokemones 0 IV en Moonani y devuelve sus coordenadas.")
    @app_commands.describe(
        nombre="Nombre completo o parcial del Pokemon",
        cantidad="Cuantos resultados mostrar (1-10)",
    )
    async def pokemon0(
        interaction: discord.Interaction,
        nombre: Optional[str] = None,
        cantidad: int = 5,
    ) -> None:
        if not 1 <= cantidad <= 10:
            await interaction.response.send_message("`cantidad` debe estar entre 1 y 10.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        try:
            results = await _search_zero_spawns(bot, nombre, cantidad)
        except Exception as exc:  # pragma: no cover
            await interaction.followup.send(f"No pude consultar Moonani IV0 en este momento: `{type(exc).__name__}: {exc}`")
            return

        if not results:
            await interaction.followup.send("No encontre pokemones 0 IV que coincidan con esos filtros.")
            return

        if len(results) == 1:
            await interaction.followup.send(embed=_build_detail_embed(results[0], source_label="Moonani IV0"))
            return

        await interaction.followup.send(embed=_build_list_embed(results, query=nombre or "", source_label="Moonani IV0"))

    @bot.tree.command(name="coords0", description="Devuelve coordenadas de 0 IV listas para copiar.")
    @app_commands.describe(
        nombre="Nombre completo o parcial del Pokemon",
        cantidad="Cuantos resultados mostrar (1-15)",
    )
    async def coords0(
        interaction: discord.Interaction,
        nombre: Optional[str] = None,
        cantidad: int = 5,
    ) -> None:
        if not 1 <= cantidad <= 15:
            await interaction.response.send_message("`cantidad` debe estar entre 1 y 15.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        try:
            results = await _search_zero_spawns(bot, nombre, cantidad)
        except Exception as exc:  # pragma: no cover
            await interaction.followup.send(f"No pude consultar Moonani IV0 en este momento: `{type(exc).__name__}: {exc}`")
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
            header = ""
            if len(lines) > 1:
                header = f"Bloque {chunk_index}/{len(chunks)}\n\n"
            await interaction.followup.send(f"{header}{chunk}")

    @bot.tree.command(name="configurar_canal", description="Configura el canal de alertas para 100 IV o 0 IV.")
    @app_commands.describe(
        tipo="Tipo de alertas que quieres enviar",
        canal="Canal donde Lucario enviara las alertas",
    )
    @app_commands.choices(
        tipo=[
            app_commands.Choice(name="100 IV", value=HUNDO_KIND),
            app_commands.Choice(name="0 IV", value=ZERO_KIND),
        ]
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def configurar_canal(
        interaction: discord.Interaction,
        tipo: app_commands.Choice[str],
        canal: discord.TextChannel,
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("Este comando solo se puede usar dentro de un servidor.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        bot.set_channel_id(interaction.guild_id, tipo.value, canal.id)
        await bot._prime_seen_cache(interaction.guild_id, tipo.value)
        await interaction.followup.send(
            f"Canal configurado para alertas de {ALERT_KIND_LABELS[tipo.value]}: {canal.mention}\n"
            "Lucario empezara a avisar solo los spawns nuevos que detecte desde ahora.",
            ephemeral=True,
        )

    @bot.tree.command(name="quitar_canal", description="Quita el canal configurado para alertas de 100 IV o 0 IV.")
    @app_commands.describe(tipo="Tipo de alertas que quieres desactivar")
    @app_commands.choices(
        tipo=[
            app_commands.Choice(name="100 IV", value=HUNDO_KIND),
            app_commands.Choice(name="0 IV", value=ZERO_KIND),
        ]
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def quitar_canal(
        interaction: discord.Interaction,
        tipo: app_commands.Choice[str],
    ) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("Este comando solo se puede usar dentro de un servidor.", ephemeral=True)
            return

        bot.clear_channel_id(interaction.guild_id, tipo.value)
        bot.seen_spawns[(interaction.guild_id, tipo.value)] = set()
        await interaction.response.send_message(
            f"Se desactivo el canal de alertas para {ALERT_KIND_LABELS[tipo.value]}.",
            ephemeral=True,
        )

    @bot.tree.command(name="ver_canales", description="Muestra los canales configurados para alertas automáticas.")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def ver_canales(interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            await interaction.response.send_message("Este comando solo se puede usar dentro de un servidor.", ephemeral=True)
            return

        hundo_channel_id = bot.get_channel_id(interaction.guild_id, HUNDO_KIND)
        zero_channel_id = bot.get_channel_id(interaction.guild_id, ZERO_KIND)

        def _format_channel(channel_id: Optional[int]) -> str:
            return f"<#{channel_id}>" if channel_id else "No configurado"

        embed = discord.Embed(title="Canales configurados", color=discord.Color.blurple())
        embed.add_field(name="100 IV", value=_format_channel(hundo_channel_id), inline=False)
        embed.add_field(name="0 IV", value=_format_channel(zero_channel_id), inline=False)
        embed.set_footer(text="Configuracion de alertas automaticas de Lucario")
        await interaction.response.send_message(embed=embed, ephemeral=True)

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
    monitor_interval_seconds = _read_int_env("LUCARIO_MONITOR_INTERVAL_SECONDS", 45)
    alert_limit_hundo = _read_int_env("LUCARIO_ALERT_LIMIT_100IV", 250)
    alert_limit_zero = _read_int_env("LUCARIO_ALERT_LIMIT_0IV", 250)

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
        monitor_interval_seconds=monitor_interval_seconds,
        alert_limit_hundo=alert_limit_hundo,
        alert_limit_zero=alert_limit_zero,
    )
    register_commands(bot)
    bot.run(token)


if __name__ == "__main__":
    main()
