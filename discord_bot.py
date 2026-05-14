import asyncio
import os
from typing import Iterable, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from moonani_client import MoonaniClient, PokemonSpawn

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


def _read_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default

    try:
        return int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"La variable {name} debe ser un numero entero.") from exc


def _format_spawn_short(index: int, spawn: PokemonSpawn) -> str:
    shiny_text = " | shiny" if spawn.shiny else ""
    return (
        f"**{index}. {discord.utils.escape_markdown(spawn.name)}** "
        f"(#{spawn.number})\n"
        f"Coords: `{spawn.coords}` | [Maps]({spawn.maps_url})\n"
        f"IV: {spawn.iv_percent}% | CP: {spawn.cp} | Nivel: {spawn.level}{shiny_text}\n"
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


def _build_detail_embed(spawn: PokemonSpawn) -> discord.Embed:
    embed = discord.Embed(
        title=f"{spawn.name} (#{spawn.number})",
        description=f"Coords: `{spawn.coords}`",
        color=discord.Color.green() if spawn.shiny else discord.Color.blurple(),
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

    if spawn.shiny:
        embed.set_footer(text="Shiny detectado por Lucario desde Moonani")
    else:
        embed.set_footer(text="Datos obtenidos por Lucario desde Moonani")

    if spawn.image_url:
        embed.set_thumbnail(url=spawn.image_url)

    return embed


def _build_list_embed(results: List[PokemonSpawn], query: str, iv_filter: int, shiny_only: bool) -> discord.Embed:
    title = "Resultados de Moonani"
    if query:
        title = f'Resultados para "{query}"'

    filters = [f"IV >= {iv_filter}%"]
    if shiny_only:
        filters.append("solo shiny")

    embed = discord.Embed(
        title=title,
        description="\n\n".join(_format_spawn_short(index, spawn) for index, spawn in enumerate(results, start=1)),
        color=discord.Color.gold() if shiny_only else discord.Color.blurple(),
    )
    embed.set_footer(text=" | ".join(filters))
    return embed


async def _search_spawns(
    bot: "LucarioDiscordBot",
    nombre: Optional[str],
    cantidad: int,
    iv_min: int,
    shiny: bool,
) -> List[PokemonSpawn]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: bot.moonani.search_pokemon(
            query=nombre or "",
            limit=cantidad,
            iv_filter=iv_min,
            shiny_only=shiny,
            page_size=bot.page_size,
            max_records=bot.max_scan_records,
        ),
    )


class LucarioDiscordBot(commands.Bot):
    def __init__(
        self,
        moonani: MoonaniClient,
        guild_id: Optional[int],
        page_size: int,
        max_scan_records: int,
    ) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.moonani = moonani
        self.guild_id = guild_id
        self.page_size = page_size
        self.max_scan_records = max_scan_records

    async def setup_hook(self) -> None:
        if self.guild_id:
            guild = discord.Object(id=self.guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            print(f"Comandos slash sincronizados en el servidor {self.guild_id}: {len(synced)}")
        else:
            synced = await self.tree.sync()
            print(f"Comandos slash globales sincronizados: {len(synced)}")


def register_commands(bot: LucarioDiscordBot) -> None:
    @bot.tree.command(name="ping", description="Comprueba si el bot esta en linea.")
    async def ping(interaction: discord.Interaction) -> None:
        latency_ms = round(bot.latency * 1000, 2)
        await interaction.response.send_message(f"Pong. Latencia aproximada: {latency_ms} ms")

    @bot.tree.command(name="pokemon", description="Busca pokemones en Moonani y devuelve sus coordenadas.")
    @app_commands.describe(
        nombre="Nombre completo o parcial del Pokemon",
        cantidad="Cuantos resultados mostrar (1-10)",
        iv_min="IV minimo a pedir al endpoint (0-100)",
        shiny="Si quieres solo resultados shiny",
        privado="Si la respuesta solo debe verla quien ejecuta el comando",
    )
    async def pokemon(
        interaction: discord.Interaction,
        nombre: Optional[str] = None,
        cantidad: int = 5,
        iv_min: int = 100,
        shiny: bool = False,
        privado: bool = False,
    ) -> None:
        if not 1 <= cantidad <= 10:
            await interaction.response.send_message("`cantidad` debe estar entre 1 y 10.", ephemeral=True)
            return
        if not 0 <= iv_min <= 100:
            await interaction.response.send_message("`iv_min` debe estar entre 0 y 100.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True, ephemeral=privado)

        try:
            results = await _search_spawns(bot, nombre, cantidad, iv_min, shiny)
        except Exception as exc:  # pragma: no cover
            await interaction.followup.send(
                f"No pude consultar Moonani en este momento: `{type(exc).__name__}: {exc}`",
                ephemeral=privado,
            )
            return

        if not results:
            await interaction.followup.send(
                "No encontre pokemones que coincidan con esos filtros.",
                ephemeral=privado,
            )
            return

        if len(results) == 1:
            await interaction.followup.send(embed=_build_detail_embed(results[0]), ephemeral=privado)
            return

        await interaction.followup.send(
            embed=_build_list_embed(results, query=nombre or "", iv_filter=iv_min, shiny_only=shiny),
            ephemeral=privado,
        )

    @bot.tree.command(name="coords", description="Devuelve un mensaje compacto con coordenadas listas para copiar.")
    @app_commands.describe(
        nombre="Nombre completo o parcial del Pokemon",
        cantidad="Cuantos resultados mostrar (1-15)",
        iv_min="IV minimo a pedir al endpoint (0-100)",
        shiny="Si quieres solo resultados shiny",
        privado="Si la respuesta solo debe verla quien ejecuta el comando",
    )
    async def coords(
        interaction: discord.Interaction,
        nombre: Optional[str] = None,
        cantidad: int = 5,
        iv_min: int = 100,
        shiny: bool = False,
        privado: bool = False,
    ) -> None:
        if not 1 <= cantidad <= 15:
            await interaction.response.send_message("`cantidad` debe estar entre 1 y 15.", ephemeral=True)
            return
        if not 0 <= iv_min <= 100:
            await interaction.response.send_message("`iv_min` debe estar entre 0 y 100.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True, ephemeral=privado)

        try:
            results = await _search_spawns(bot, nombre, cantidad, iv_min, shiny)
        except Exception as exc:  # pragma: no cover
            await interaction.followup.send(
                f"No pude consultar Moonani en este momento: `{type(exc).__name__}: {exc}`",
                ephemeral=privado,
            )
            return

        if not results:
            await interaction.followup.send(
                "No encontre coordenadas con esos filtros.",
                ephemeral=privado,
            )
            return

        lines = []
        for index, spawn in enumerate(results, start=1):
            shiny_text = " | shiny" if spawn.shiny else ""
            lines.append(
                f"{index}. {spawn.name} (#{spawn.number}){shiny_text}\n"
                f"Coords: `{spawn.coords}`\n"
                f"Maps: {spawn.maps_url}\n"
                f"IV: {spawn.iv_percent}% | CP: {spawn.cp} | Fin: {spawn.end_time}"
            )

        chunks = _chunk_lines(lines)
        for chunk_index, chunk in enumerate(chunks, start=1):
            header = ""
            if len(lines) > 1:
                header = f"Bloque {chunk_index}/{len(chunks)}\n\n"
            await interaction.followup.send(f"{header}{chunk}", ephemeral=privado)

    @bot.tree.error
    async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        message = f"Ocurrio un error al ejecutar el comando: `{type(error).__name__}`"
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


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
    resolve_countries = os.getenv("MOONANI_RESOLVE_COUNTRIES", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    geocoder_endpoint = os.getenv("MOONANI_GEOCODER_ENDPOINT", "").strip()
    geocoder_user_agent = os.getenv("MOONANI_GEOCODER_USER_AGENT", "").strip() or "Lucario Discord Bot/1.0"

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
    )
    register_commands(bot)
    bot.run(token)


if __name__ == "__main__":
    main()
