"""Grave Without a Stone seed catalogue bot.

Submitting seeds happens on a panel: a pinned message with one button per ranking.
A button opens a form for the seed, why it got that ranking, and images. Instant
Complete asks for the map, the building and where the flare gun is.

Slash commands:
  /panel    (admins) post the submission panel in this channel
  /lookup   check whether a seed is already catalogued
  /list     browse catalogued seeds, optionally by ranking
  /stats    how many seeds are in each ranking
  /export   download the whole catalogue as a CSV
  /remove   (moderators) delete a seed and its channel post
"""
import io
import os
import time
from datetime import datetime, timezone

import aiohttp
import discord
from discord import app_commands
from dotenv import load_dotenv

from seeddb import TIERS, SeedDB

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")  # optional: makes commands appear instantly in one server
DB_PATH = os.getenv("DB_PATH", "seeds.db")
WEBHOOKS = {t: os.getenv(f"WEBHOOK_{t.upper()}", "").strip() for t in TIERS}
MAPS = [m.strip() for m in os.getenv("MAPS", "").split(",") if m.strip()][:25]
MAX_IMAGES = 10
IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".gif", ".webp")

TIER_CHOICES = [app_commands.Choice(name=v["label"], value=k) for k, v in TIERS.items()]

db = SeedDB(DB_PATH)


# ---------- embeds ----------

def seed_embed(s, image_name: str | None = None) -> discord.Embed:
    tier = TIERS[s.tier]
    e = discord.Embed(title=f"Seed: {s.seed}", color=tier["color"])
    e.add_field(name="Ranking", value=tier["label"], inline=True)
    e.add_field(name="Submitted by", value=f"<@{s.submitter_id}>", inline=True)
    if s.tier == "instant":
        e.add_field(name="Map", value=s.map, inline=True)
        e.add_field(name="Building", value=s.building, inline=True)
        e.add_field(name="Where the flare gun is", value=s.location[:1024], inline=False)
    else:
        e.add_field(name=f"Why it's {tier['label']}", value=s.reason[:1024], inline=False)
    if image_name:
        e.set_image(url=f"attachment://{image_name}")
    elif s.images:
        e.set_image(url=s.images.split("\n")[0])
    e.timestamp = datetime.fromtimestamp(s.created_at, tz=timezone.utc)
    e.set_footer(text=f"Catalogue entry #{s.id}")
    return e


def panel_embed() -> discord.Embed:
    e = discord.Embed(
        title="Seed Submissions",
        description=(
            "Found a seed worth sharing? Pick its ranking below and fill in the form.\n\n"
            "**Every seed:** the seed and why it earned that ranking. Images are optional "
            f"(up to {MAX_IMAGES}).\n"
            "**Instant Complete:** the map, the building, and exactly where the flare gun is.\n\n"
            "Seeds that are already catalogued are turned away, with a link to the existing post. "
            "Use **Look up a seed** to check first."
        ),
        color=0x5865F2,
    )
    e.set_footer(text="Grave Without a Stone seed catalogue")
    return e


def duplicate_message(existing) -> str:
    where = f" Posted here: {existing.message_url}" if existing.message_url else ""
    return (f"**{existing.seed}** is already catalogued as "
            f"**{TIERS[existing.tier]['label']}** by {existing.submitter_name}.{where}")


# ---------- the bot ----------

class SeedBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.http_session: aiohttp.ClientSession | None = None

    async def setup_hook(self):
        self.http_session = aiohttp.ClientSession()
        self.add_view(PanelView())  # keeps panel buttons working after restarts
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def close(self):
        if self.http_session:
            await self.http_session.close()
        await super().close()

    def webhook(self, tier: str) -> discord.Webhook | None:
        url = WEBHOOKS.get(tier)
        if not url:
            return None
        return discord.Webhook.from_url(url, session=self.http_session)


bot = SeedBot()


@bot.event
async def on_ready():
    missing = [t for t, u in WEBHOOKS.items() if not u]
    print(f"Logged in as {bot.user}. Seeds catalogued: {sum(db.counts().values())}")
    if missing:
        print(f"Warning: no webhook set for: {', '.join(missing)}")


async def catalogue(interaction: discord.Interaction, *, seed: str, tier: str, reason: str,
                    map=None, building=None, location=None, images=()):
    """Save a seed and post it to its ranking channel. The interaction must already be deferred."""
    label = TIERS[tier]["label"]
    send = interaction.followup.send

    existing = db.get(seed)
    if existing:
        await send(duplicate_message(existing), ephemeral=True)
        return

    hook = bot.webhook(tier)
    if hook is None:
        await send(f"No webhook is set up for **{label}** yet. Ask a server admin to add "
                   f"WEBHOOK_{tier.upper()} to the bot's .env file.", ephemeral=True)
        return

    bad = [a.filename for a in images if not a.filename.lower().endswith(IMAGE_TYPES)]
    if bad:
        await send(f"Only images can be attached (PNG, JPG, GIF, WEBP). Remove: {', '.join(bad)}",
                   ephemeral=True)
        return

    try:
        entry = db.add(seed, tier, reason, interaction.user.id, str(interaction.user),
                       map=map, building=building, location=location)
    except KeyError:
        await send("Someone catalogued that seed a moment ago.", ephemeral=True)
        return
    except ValueError as err:
        await send(str(err), ephemeral=True)
        return

    try:
        files = [await a.to_file() for a in images]
        msg = await hook.send(
            embed=seed_embed(entry, image_name=files[0].filename if files else None),
            files=files, wait=True, allowed_mentions=discord.AllowedMentions.none(),
        )
        db.set_message(entry.id, msg.id, msg.jump_url, [a.url for a in msg.attachments])
    except discord.HTTPException as err:
        db.remove(seed)  # keep the database and the channels in step
        if err.status == 413:
            reason_text = "the images are too large together. Try fewer or smaller images"
        else:
            reason_text = f"Discord returned error {err.status}. Check that the webhook URL is still valid"
        await send(f"Couldn't post to the {label} channel: {reason_text}. The seed wasn't saved.",
                   ephemeral=True)
        return

    await send(f"Catalogued **{entry.seed}** as **{label}**. {msg.jump_url}", ephemeral=True)


# ---------- the panel ----------

class SeedForm(discord.ui.Modal):
    """The form a panel button opens. Discord allows five fields per form."""

    def __init__(self, tier: str):
        self.tier = tier
        label = TIERS[tier]["label"]
        super().__init__(title=f"Submit a {label} seed", timeout=900)

        self.seed = discord.ui.TextInput(max_length=100, placeholder="The seed exactly as the game shows it")
        self.add_item(discord.ui.Label(text="Seed", component=self.seed))

        if tier == "instant":
            if MAPS:
                self.map = discord.ui.Select(
                    options=[discord.SelectOption(label=m) for m in MAPS], placeholder="Pick the map")
            else:
                self.map = discord.ui.TextInput(max_length=100)
            self.add_item(discord.ui.Label(text="Map", component=self.map))
            self.building = discord.ui.TextInput(max_length=100, placeholder="e.g. the church")
            self.add_item(discord.ui.Label(text="Building", component=self.building))
            self.location = discord.ui.TextInput(
                style=discord.TextStyle.paragraph, max_length=500,
                placeholder="Floor, room and landmark, e.g. upstairs bedroom, under the bed")
            self.add_item(discord.ui.Label(text="Where the flare gun is", component=self.location))
        else:
            self.reason = discord.ui.TextInput(
                style=discord.TextStyle.paragraph, min_length=3, max_length=1000,
                placeholder="What makes it this good (or this bad)?")
            self.add_item(discord.ui.Label(text=f"Why is this seed {label}?", component=self.reason))

        self.images = discord.ui.FileUpload(required=False, max_values=MAX_IMAGES)
        self.add_item(discord.ui.Label(
            text="Images", description=f"Optional, up to {MAX_IMAGES} screenshots",
            component=self.images))

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        fields = {"seed": self.seed.value, "tier": self.tier, "images": self.images.values}
        if self.tier == "instant":
            map_value = self.map.values[0] if isinstance(self.map, discord.ui.Select) else self.map.value
            fields.update(reason="Instant complete", map=map_value,
                          building=self.building.value, location=self.location.value)
        else:
            fields["reason"] = self.reason.value
        await catalogue(interaction, **fields)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        print(f"Form error: {error!r}")
        msg = "Something went wrong saving that seed. Please try again."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


class LookupForm(discord.ui.Modal, title="Look up a seed"):
    seed = discord.ui.TextInput(label="Seed", max_length=100)

    async def on_submit(self, interaction: discord.Interaction):
        await send_lookup(interaction, self.seed.value)


def tier_button(tier: str, style: discord.ButtonStyle, row: int):
    async def callback(interaction: discord.Interaction):
        await interaction.response.send_modal(SeedForm(tier))
    b = discord.ui.Button(label=TIERS[tier]["label"], style=style,
                          custom_id=f"seedpanel:{tier}", row=row)
    b.callback = callback
    return b


class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        grey, green, blue, red = (discord.ButtonStyle.secondary, discord.ButtonStyle.success,
                                  discord.ButtonStyle.primary, discord.ButtonStyle.danger)
        for tier, style in (("mediocre", grey), ("good", green), ("great", blue),
                            ("amazing", blue), ("perfect", green)):
            self.add_item(tier_button(tier, style, row=0))
        self.add_item(tier_button("instant", red, row=1))

    @discord.ui.button(label="Look up a seed", style=discord.ButtonStyle.secondary,
                       custom_id="seedpanel:lookup", row=1)
    async def lookup_button(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(LookupForm())


# ---------- commands ----------

@bot.tree.command(description="Post the seed submission panel in this channel (admins)")
@app_commands.default_permissions(manage_guild=True)
async def panel(interaction: discord.Interaction):
    await interaction.channel.send(embed=panel_embed(), view=PanelView())
    await interaction.response.send_message(
        "Panel posted. Pin it so it stays easy to find.", ephemeral=True)


async def send_lookup(interaction: discord.Interaction, seed: str):
    s = db.get(seed)
    if not s:
        await interaction.response.send_message(
            f"**{seed}** isn't catalogued yet. Use the submission panel to add it.", ephemeral=True)
        return
    await interaction.response.send_message(content=s.message_url or None,
                                            embed=seed_embed(s), ephemeral=True)


@bot.tree.command(description="Check whether a seed is already catalogued")
async def lookup(interaction: discord.Interaction, seed: str):
    await send_lookup(interaction, seed)


@bot.tree.command(name="list", description="Browse catalogued seeds")
@app_commands.describe(ranking="Only show this ranking", page="Page number (25 per page)")
@app_commands.choices(ranking=TIER_CHOICES)
async def list_cmd(interaction: discord.Interaction,
                   ranking: app_commands.Choice[str] | None = None,
                   page: app_commands.Range[int, 1, 1000] = 1):
    tier = ranking.value if ranking else None
    rows = db.list(tier=tier, limit=25, offset=(page - 1) * 25)
    title = f"{ranking.name if ranking else 'All'} seeds, page {page}"
    if not rows:
        await interaction.response.send_message(f"{title}: nothing here yet.", ephemeral=True)
        return
    lines = []
    for s in rows:
        line = f"`{s.seed}` · **{TIERS[s.tier]['label']}**"
        if s.tier == "instant":
            line += f" · {s.map} / {s.building}"
        if s.message_url:
            line += f" · [post]({s.message_url})"
        lines.append(line)
    e = discord.Embed(title=title, description="\n".join(lines)[:4096],
                      color=TIERS[tier]["color"] if tier else 0x5865F2)
    await interaction.response.send_message(embed=e, ephemeral=True)


@bot.tree.command(description="How many seeds are in each ranking")
async def stats(interaction: discord.Interaction):
    c = db.counts()
    e = discord.Embed(title="Seed catalogue", color=0x5865F2)
    for t, v in TIERS.items():
        e.add_field(name=v["label"], value=str(c[t]), inline=True)
    e.set_footer(text=f"Total: {sum(c.values())}")
    await interaction.response.send_message(embed=e)


@bot.tree.command(description="Download the whole catalogue as a spreadsheet (CSV)")
async def export(interaction: discord.Interaction):
    data = db.export_csv().encode("utf-8")
    name = f"grave-seeds-{time.strftime('%Y-%m-%d')}.csv"
    await interaction.response.send_message(
        file=discord.File(io.BytesIO(data), filename=name), ephemeral=True)


@bot.tree.command(description="Remove a seed from the catalogue (moderators)")
@app_commands.default_permissions(manage_messages=True)
async def remove(interaction: discord.Interaction, seed: str):
    s = db.remove(seed)
    if not s:
        await interaction.response.send_message(f"**{seed}** isn't in the catalogue.", ephemeral=True)
        return
    note = ""
    hook = bot.webhook(s.tier)
    if hook and s.message_id:
        try:
            await hook.delete_message(s.message_id)
        except discord.HTTPException:
            note = " The channel post couldn't be deleted, so remove it by hand."
    await interaction.response.send_message(
        f"Removed **{s.seed}** ({TIERS[s.tier]['label']}).{note}", ephemeral=True)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN is missing. Copy .env.example to .env and fill it in.")
    bot.run(TOKEN)
