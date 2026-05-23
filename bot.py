from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Iterable, Sequence

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

from moonani_utils import normalize_name
from poketest import PokemonSpawn, fetch_hundo_pokemon, search_hundo_pokemon
from questtest import QUEST_AUTOCOMPLETE_NAMES, search_quests
from raidtest import search_raids
from rockettest import search_rockets

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger("lucario-bot")

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID", "").strip()
MOONANI_TIMEOUT = int(os.getenv("MOONANI_TIMEOUT", "20"))
MOONANI_PAGE_SIZE = int(os.getenv("MOONANI_PAGE_SIZE", "100"))
MOONANI_MAX_SCAN_RECORDS = int(os.getenv("MOONANI_MAX_SCAN_RECORDS", "10000"))
LUCARIO_SETTINGS_PATH = Path(
    os.getenv("LUCARIO_SETTINGS_PATH", "lucario_guild_settings.json")
)
LUCARIO_MONITOR_INTERVAL_SECONDS = int(
    os.getenv("LUCARIO_MONITOR_INTERVAL_SECONDS", "45")
)
LUCARIO_ALERT_LIMIT_100IV = int(os.getenv("LUCARIO_ALERT_LIMIT_100IV", "250"))

COMMAND_GUILD = (
    discord.Object(id=int(DISCORD_GUILD_ID)) if DISCORD_GUILD_ID else None
)

MAX_SEARCH_RESULTS = 5
RECENT_ALERT_HISTORY_LIMIT = max(50, LUCARIO_ALERT_LIMIT_100IV)


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"subscriptions": {}, "recent_alerts": {}}

        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            LOGGER.warning(
                "No se pudo leer %s, se recreara desde cero.",
                self.path,
            )
            return {"subscriptions": {}, "recent_alerts": {}}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temp_path.write_text(
            json.dumps(self.data, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self.path)

    def add_subscription(self, channel_id: int, pokemon_name: str) -> bool:
        pokemon_key = normalize_name(pokemon_name)
        label = pokemon_name.strip().title()
        channel_key = str(channel_id)
        subscriptions = self.data.setdefault("subscriptions", {})
        channel_subscriptions = subscriptions.setdefault(channel_key, [])

        for item in channel_subscriptions:
            if item["pokemon_key"] == pokemon_key:
                return False

        channel_subscriptions.append(
            {
                "pokemon_key": pokemon_key,
                "pokemon_label": label,
            }
        )
        channel_subscriptions.sort(key=lambda item: item["pokemon_label"])
        self.save()
        return True

    def remove_subscription(self, channel_id: int, pokemon_name: str) -> bool:
        pokemon_key = normalize_name(pokemon_name)
        channel_key = str(channel_id)
        subscriptions = self.data.setdefault("subscriptions", {})
        channel_subscriptions = subscriptions.get(channel_key, [])

        remaining = [
            item
            for item in channel_subscriptions
            if item["pokemon_key"] != pokemon_key
        ]

        if len(remaining) == len(channel_subscriptions):
            return False

        if remaining:
            subscriptions[channel_key] = remaining
        else:
            subscriptions.pop(channel_key, None)

        self.data["recent_alerts"].pop(
            self.subscription_key(channel_id, pokemon_key),
            None,
        )
        self.save()
        return True

    def list_channel_subscriptions(self, channel_id: int) -> list[dict]:
        return list(
            self.data.setdefault("subscriptions", {}).get(str(channel_id), [])
        )

    def list_guild_subscriptions(
        self,
        guild_channels: Iterable[discord.abc.GuildChannel],
    ) -> list[tuple[discord.abc.GuildChannel, list[dict]]]:
        channels_by_id = {str(channel.id): channel for channel in guild_channels}
        rows: list[tuple[discord.abc.GuildChannel, list[dict]]] = []

        for channel_id, subscriptions in self.data.setdefault(
            "subscriptions", {}
        ).items():
            channel = channels_by_id.get(channel_id)
            if channel is not None:
                rows.append((channel, list(subscriptions)))

        rows.sort(key=lambda row: row[0].position)
        return rows

    def all_subscriptions(self) -> list[tuple[int, dict]]:
        rows: list[tuple[int, dict]] = []
        for channel_id, subscriptions in self.data.setdefault(
            "subscriptions", {}
        ).items():
            for subscription in subscriptions:
                rows.append((int(channel_id), dict(subscription)))
        return rows

    def subscription_key(self, channel_id: int, pokemon_key: str) -> str:
        return f"{channel_id}:{pokemon_key}"

    def has_recent_alert(self, channel_id: int, pokemon_key: str, alert: str) -> bool:
        key = self.subscription_key(channel_id, pokemon_key)
        recent = self.data.setdefault("recent_alerts", {}).get(key, [])
        return alert in recent

    def remember_alerts(
        self,
        channel_id: int,
        pokemon_key: str,
        alerts: Sequence[str],
    ) -> None:
        key = self.subscription_key(channel_id, pokemon_key)
        recent_alerts = self.data.setdefault("recent_alerts", {})
        known = recent_alerts.setdefault(key, [])
        for alert in alerts:
            if alert not in known:
                known.append(alert)
        recent_alerts[key] = known[-RECENT_ALERT_HISTORY_LIMIT:]
        self.save()


class LucarioBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.settings = SettingsStore(LUCARIO_SETTINGS_PATH)
        self.monitor_lock = asyncio.Lock()

    async def setup_hook(self) -> None:
        if COMMAND_GUILD is not None:
            await self.tree.sync(guild=COMMAND_GUILD)
            LOGGER.info("Comandos sincronizados para guild %s", DISCORD_GUILD_ID)
        else:
            await self.tree.sync()
            LOGGER.info("Comandos globales sincronizados")

        if not self.hundo_monitor.is_running():
            self.hundo_monitor.start()

    async def on_ready(self) -> None:
        LOGGER.info("Bot listo como %s (%s)", self.user, self.user.id)

    @tasks.loop(seconds=LUCARIO_MONITOR_INTERVAL_SECONDS)
    async def hundo_monitor(self) -> None:
        async with self.monitor_lock:
            subscriptions = self.settings.all_subscriptions()
            if not subscriptions:
                return

            try:
                spawns = await asyncio.to_thread(
                    fetch_hundo_pokemon,
                    MOONANI_TIMEOUT,
                    MOONANI_PAGE_SIZE,
                    MOONANI_MAX_SCAN_RECORDS,
                )
            except Exception:
                LOGGER.exception("Fallo el monitoreo de IV100")
                return

            for channel_id, subscription in subscriptions:
                matches = [
                    spawn
                    for spawn in spawns
                    if subscription_matches_spawn(
                        subscription["pokemon_key"],
                        spawn.name,
                    )
                ]

                unseen_matches = [
                    spawn
                    for spawn in matches
                    if not self.settings.has_recent_alert(
                        channel_id,
                        subscription["pokemon_key"],
                        spawn.alert_key,
                    )
                ]

                if not unseen_matches:
                    continue

                channel = self.get_channel(channel_id)
                if channel is None:
                    try:
                        channel = await self.fetch_channel(channel_id)
                    except Exception:
                        LOGGER.warning("No se pudo acceder al canal %s", channel_id)
                        continue

                if not isinstance(channel, discord.abc.Messageable):
                    continue

                pages = render_pokemon_pages(
                    unseen_matches,
                    f"Seguimiento IV100: {subscription['pokemon_label']}",
                )

                for page in pages:
                    await channel.send(page, suppress_embeds=True)

                self.settings.remember_alerts(
                    channel_id,
                    subscription["pokemon_key"],
                    [spawn.alert_key for spawn in unseen_matches],
                )

    @hundo_monitor.before_loop
    async def before_hundo_monitor(self) -> None:
        await self.wait_until_ready()


bot = LucarioBot()


def format_coords_block(coords: str) -> str:
    return f"```txt\n{coords}\n```"


def subscription_matches_spawn(pokemon_key: str, spawn_name: str) -> bool:
    normalized_spawn = normalize_name(spawn_name)
    return (
        normalized_spawn == pokemon_key
        or normalized_spawn.startswith(f"{pokemon_key} ")
    )


def pokemon_section(index: int, spawn: PokemonSpawn) -> str:
    shiny = " | Shiny" if spawn.shiny else ""
    return "\n".join(
        [
            f"**{index}. {spawn.name}** #{spawn.number}",
            (
                f"CP {spawn.cp} | Nivel {spawn.level} | "
                f"IV {spawn.attack}/{spawn.defense}/{spawn.hp} | "
                f"Pais {spawn.country}{shiny}"
            ),
            f"Inicio: {spawn.start_time}",
            f"Fin: {spawn.end_time}",
            format_coords_block(spawn.coords),
            f"Maps: <{spawn.maps_url}>",
        ]
    )


def rocket_section(index: int, rocket) -> str:
    role = rocket.leader or rocket.grunt_type or rocket.name
    return "\n".join(
        [
            f"**{index}. {rocket.name}**",
            f"Filtro: {role} | Poder {rocket.power} | Pais {rocket.country}",
            f"Inicio: {rocket.start_time}",
            f"Fin: {rocket.end_time}",
            format_coords_block(rocket.coords),
            f"Maps: <{rocket.maps_url}>",
        ]
    )


def raid_section(index: int, raid) -> str:
    return "\n".join(
        [
            f"**{index}. {raid.name}** #{raid.number}",
            f"Nivel {raid.level} | Pais {raid.country}",
            f"Inicio: {raid.start_time}",
            f"Fin: {raid.end_time}",
            format_coords_block(raid.coords),
            f"Maps: <{raid.maps_url}>",
        ]
    )


def quest_section(index: int, quest) -> str:
    return "\n".join(
        [
            f"**{index}. {quest.pokemon}** #{quest.pokemon_id}",
            f"Mision: {quest.quest}",
            f"Pais {quest.country}",
            f"Inicio: {quest.start_time}",
            f"Fin: {quest.end_time}",
            format_coords_block(quest.coords),
            f"Maps: <{quest.maps_url}>",
        ]
    )


def build_pages(
    title: str,
    sections: Sequence[str],
    total_found: int,
    page_limit: int = 1800,
) -> list[str]:
    header = f"**{title}**\nResultados mostrados: {len(sections)} de {total_found}"
    pages: list[str] = []
    current = header

    for section in sections:
        candidate = f"{current}\n\n{section}"
        if len(candidate) > page_limit and current != header:
            pages.append(current)
            current = f"{header}\n\n{section}"
        else:
            current = candidate

    pages.append(current)
    return pages


def render_pokemon_pages(
    spawns: Sequence[PokemonSpawn],
    title: str,
    display_limit: int | None = None,
) -> list[str]:
    limited = list(spawns if display_limit is None else spawns[:display_limit])
    sections = [
        pokemon_section(index, spawn)
        for index, spawn in enumerate(limited, start=1)
    ]
    return build_pages(title, sections, len(spawns))


async def send_pages(
    interaction: discord.Interaction,
    pages: Sequence[str],
) -> None:
    first, *rest = pages
    await interaction.followup.send(first, suppress_embeds=True)
    for page in rest:
        await interaction.followup.send(page, suppress_embeds=True)

@bot.tree.command(
    name="buscar_pokemon",
    description="Busca Pokemon 100 IV por nombre",
    guild=COMMAND_GUILD,
)
@app_commands.describe(nombre="Nombre del Pokemon a buscar")
async def buscar_pokemon(
    interaction: discord.Interaction,
    nombre: str,
) -> None:
    await interaction.response.defer(thinking=True)

    matches = await asyncio.to_thread(
        search_hundo_pokemon,
        nombre,
        MOONANI_TIMEOUT,
        MOONANI_PAGE_SIZE,
        MOONANI_MAX_SCAN_RECORDS,
        MAX_SEARCH_RESULTS,
    )

    if not matches:
        await interaction.followup.send(
            f"No encontre IV100 activos para `{nombre}`.",
            suppress_embeds=True,
        )
        return

    pages = render_pokemon_pages(matches, f"Busqueda IV100: {nombre}", MAX_SEARCH_RESULTS)
    await send_pages(interaction, pages)


@bot.tree.command(
    name="agregar_seguimiento",
    description="Activa seguimiento IV100 de un Pokemon en un canal",
    guild=COMMAND_GUILD,
)
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    pokemon="Pokemon a seguir",
    canal="Canal donde se enviaran los avisos. Si lo omites, usa el actual",
)
async def agregar_seguimiento(
    interaction: discord.Interaction,
    pokemon: str,
    canal: discord.TextChannel | None = None,
) -> None:
    channel = canal or interaction.channel
    if channel is None or not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message(
            "No pude determinar el canal para guardar el seguimiento.",
            ephemeral=True,
        )
        return

    added = bot.settings.add_subscription(channel.id, pokemon)

    if not added:
        await interaction.response.send_message(
            f"`{pokemon}` ya estaba en seguimiento para {channel.mention}.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        f"Seguimiento activado para `{pokemon}` en {channel.mention}.",
        ephemeral=True,
    )


@bot.tree.command(
    name="quitar_seguimiento",
    description="Quita seguimiento IV100 de un Pokemon en un canal",
    guild=COMMAND_GUILD,
)
@app_commands.default_permissions(manage_guild=True)
@app_commands.describe(
    pokemon="Pokemon a quitar",
    canal="Canal del seguimiento. Si lo omites, usa el actual",
)
async def quitar_seguimiento(
    interaction: discord.Interaction,
    pokemon: str,
    canal: discord.TextChannel | None = None,
) -> None:
    channel = canal or interaction.channel
    if channel is None or not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message(
            "No pude determinar el canal para quitar el seguimiento.",
            ephemeral=True,
        )
        return

    removed = bot.settings.remove_subscription(channel.id, pokemon)

    if not removed:
        await interaction.response.send_message(
            f"No habia seguimiento de `{pokemon}` en {channel.mention}.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        f"Seguimiento quitado para `{pokemon}` en {channel.mention}.",
        ephemeral=True,
    )


@bot.tree.command(
    name="ver_seguimientos",
    description="Muestra los seguimientos IV100 del servidor",
    guild=COMMAND_GUILD,
)
@app_commands.default_permissions(manage_guild=True)
async def ver_seguimientos(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message(
            "Este comando solo funciona dentro de un servidor.",
            ephemeral=True,
        )
        return

    rows = bot.settings.list_guild_subscriptions(interaction.guild.channels)
    if not rows:
        await interaction.response.send_message(
            "No hay seguimientos configurados en este servidor.",
            ephemeral=True,
        )
        return

    lines = ["**Seguimientos IV100**"]
    for channel, subscriptions in rows:
        names = ", ".join(item["pokemon_label"] for item in subscriptions)
        lines.append(f"{channel.mention}: {names}")

    await interaction.response.send_message(
        "\n".join(lines),
        ephemeral=True,
        suppress_embeds=True,
    )


@bot.tree.command(
    name="rocket",
    description="Busca Rockets por tipo o lider",
    guild=COMMAND_GUILD,
)
@app_commands.describe(filtro="Ejemplo: giovanni, arlo, water, fire")
async def rocket(
    interaction: discord.Interaction,
    filtro: str,
) -> None:
    await interaction.response.defer(thinking=True)

    matches = await asyncio.to_thread(
        search_rockets,
        filtro,
        MOONANI_TIMEOUT,
        MAX_SEARCH_RESULTS,
    )

    if not matches:
        await interaction.followup.send(
            f"No encontre Rockets para `{filtro}`.",
            suppress_embeds=True,
        )
        return

    sections = [
        rocket_section(index, rocket_item)
        for index, rocket_item in enumerate(matches, start=1)
    ]
    pages = build_pages(f"Busqueda Rocket: {filtro}", sections, len(matches))
    await send_pages(interaction, pages)


@bot.tree.command(
    name="raid",
    description="Busca raids por nombre",
    guild=COMMAND_GUILD,
)
@app_commands.describe(nombre="Nombre del raid, por ejemplo Rayquaza")
async def raid(
    interaction: discord.Interaction,
    nombre: str,
) -> None:
    await interaction.response.defer(thinking=True)

    matches = await asyncio.to_thread(
        search_raids,
        nombre,
        MOONANI_TIMEOUT,
        MAX_SEARCH_RESULTS,
    )

    if not matches:
        await interaction.followup.send(
            f"No encontre raids para `{nombre}`.",
            suppress_embeds=True,
        )
        return

    sections = [
        raid_section(index, raid_item)
        for index, raid_item in enumerate(matches, start=1)
    ]
    pages = build_pages(f"Busqueda Raid: {nombre}", sections, len(matches))
    await send_pages(interaction, pages)


@bot.tree.command(
    name="quest",
    description="Busca quests de Kecleon, Pikachu, Psyduck, Snorlax o Spinda",
    guild=COMMAND_GUILD,
)
@app_commands.describe(pokemon="Pokemon de mision")
async def quest(
    interaction: discord.Interaction,
    pokemon: str,
) -> None:
    await interaction.response.defer(thinking=True)

    matches = await asyncio.to_thread(
        search_quests,
        pokemon,
        MOONANI_TIMEOUT,
        MAX_SEARCH_RESULTS,
    )

    if not matches:
        await interaction.followup.send(
            (
                "No encontre quests para ese filtro. "
                "Usa Kecleon, Pikachu, Psyduck, Snorlax o Spinda."
            ),
            suppress_embeds=True,
        )
        return

    sections = [
        quest_section(index, quest_item)
        for index, quest_item in enumerate(matches, start=1)
    ]
    pages = build_pages(f"Busqueda Quest: {pokemon}", sections, len(matches))
    await send_pages(interaction, pages)


@quest.autocomplete("pokemon")
async def quest_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    normalized = current.casefold()
    options = [
        name
        for name in QUEST_AUTOCOMPLETE_NAMES
        if not normalized or normalized in name.casefold()
    ]
    return [
        app_commands.Choice(name=name, value=name)
        for name in options[:25]
    ]


def main() -> None:
    if not DISCORD_BOT_TOKEN:
        raise RuntimeError("Falta DISCORD_BOT_TOKEN en el entorno.")

    bot.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
