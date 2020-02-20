import typing
import asyncpg
import discord

from config import config
from discord.ext import commands


class Starboard(commands.Cog):
    """The Starboard. If a message on the Democraciv Guild has at least 4 :star: reactions,
    it will be posted to the Starboard channel and in a weekly summary to the subreddit every Saturday."""

    def __init__(self, bot):
        self.bot = bot
        self.star_emoji = config.STARBOARD_STAR_EMOJI
        self.star_threshold = config.STARBOARD_MIN_STARS

    @property
    def starboard_channel(self) -> typing.Optional[discord.TextChannel]:
        return self.bot.democraciv_guild_object.get_channel(config.STARBOARD_CHANNEL)

    def get_starboard_embed(self, message: discord.Message, stars: int) -> discord.Embed:

        footer_text = f"{stars} star" if stars == 1 else f"{stars} stars"

        embed = self.bot.embeds.embed_builder(title="", description=message.content,
                                              colour=0xFFAC33, has_footer=False)
        embed.set_footer(text=footer_text, icon_url="https://cdn.discordapp.com/attachments/"
                                                    "639549494693724170/679824104190115911/star.png")
        embed.set_author(name=message.author.display_name, icon_url=message.author.avatar_url_as(format='png'))
        embed.add_field(name="Original", value=f"[Jump]({message.jump_url})", inline=False)

        if message.embeds:
            data = message.embeds[0]
            if data.type == 'image':
                embed.set_image(url=data.url)

        if message.attachments:
            file = message.attachments[0]
            if file.url.lower().endswith(('png', 'jpeg', 'jpg', 'gif', 'webp')):
                embed.set_image(url=file.url)
            else:
                embed.add_field(name='Attachment', value=f'[{file.filename}]({file.url})', inline=False)

        return embed

    async def verify_reaction(self, payload: discord.RawReactionActionEvent, message: discord.Message,
                              channel: discord.abc.GuildChannel) -> bool:
        if str(payload.emoji) != self.star_emoji:
            return False

        if payload.guild_id != self.bot.democraciv_guild_object.id:
            return False

        if payload.channel_id == self.starboard_channel.id:
            return False

        if await self.bot.checks.is_channel_excluded(self.bot.democraciv_guild_object.id, payload.channel_id):
            return False

        if not isinstance(channel, discord.TextChannel):
            return False

        if payload.user_id == message.author.id:
            return False

        return True

    @commands.Cog.listener(name='on_raw_reaction_add')
    async def star_listener(self, payload: discord.RawReactionActionEvent):
        channel = self.bot.democraciv_guild_object.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)

        if not await self.verify_reaction(payload, message, channel):
            return

        starrer = self.bot.democraciv_guild_object.get_member(payload.user_id)

        await self.star_message(message, starrer)

    @commands.Cog.listener(name='on_raw_reaction_remove')
    async def unstar_listener(self, payload: discord.RawReactionActionEvent):
        channel = self.bot.democraciv_guild_object.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)

        if not await self.verify_reaction(payload, message, channel):
            return

        starrer = self.bot.democraciv_guild_object.get_member(payload.user_id)

        await self.unstar_message(message, starrer)

    async def star_message(self, message: discord.Message, starrer: discord.Member):
        query = "INSERT INTO starboard_entries (author_id, message_id, message_content, channel_id, guild_id, " \
                "message_creation_date) VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT DO NOTHING RETURNING id"

        entry_id = await self.bot.db.fetchval(query,
                                              message.author.id, message.id, message.clean_content,
                                              message.channel.id, message.guild.id, message.created_at)

        if entry_id is None:
            entry_id = await self.bot.db.fetchval("SELECT id FROM starboard_entries WHERE message_id = $1", message.id)

        try:
            await self.bot.db.execute("INSERT INTO starboard_starrers (entry_id, starrer_id) VALUES ($1, $2)",
                                      entry_id, starrer.id)
        except asyncpg.UniqueViolationError:
            return

        amount_of_stars = await self.bot.db.fetchval("SELECT COUNT(*) FROM starboard_starrers WHERE entry_id = $1",
                                                     entry_id)

        if amount_of_stars < self.star_threshold:
            return

        # Send embed to starboard channel or update amount of stars in existing embed
        bot_message = await self.bot.db.fetchval("SELECT starboard_message_id FROM starboard_entries "
                                                 "WHERE id = $1", entry_id)

        embed = self.get_starboard_embed(message, amount_of_stars)

        if bot_message is None:
            # Send new message
            new_bot_message = await self.starboard_channel.send(embed=embed)
            await self.bot.db.execute("UPDATE starboard_entries SET starboard_message_id = $1 WHERE id = $2",
                                      new_bot_message.id, entry_id)

        else:
            # Update star amount
            try:
                old_bot_message = await self.starboard_channel.fetch_message(bot_message)
            except discord.NotFound:
                await self.bot.db.execute("DELETE FROM starboard_entries WHERE id = $1", entry_id)
            else:
                await old_bot_message.edit(embed=embed)

    async def unstar_message(self, message: discord.Message, starrer: discord.Member):
        query = """DELETE FROM starboard_starrers USING starboard_entries starboard_entry
                   WHERE starboard_entry.message_id = $1 AND starboard_entry.id = starboard_starrers.entry_id 
                   AND starboard_starrers.starrer_id = $2 RETURNING starboard_starrers.entry_id,
                    starboard_entry.starboard_message_id"""

        entry = await self.bot.db.fetchrow(query, message.id, starrer.id)

        if entry is None:
            # Starboard message was removed and database entry cleared
            return

        entry_id = entry[0]
        bot_message = entry[1]

        if bot_message is None:
            return

        amount_of_stars = await self.bot.db.fetchval("SELECT COUNT(*) FROM starboard_starrers WHERE entry_id = $1",
                                                     entry_id)

        try:
            old_bot_message = await self.starboard_channel.fetch_message(bot_message)
        except discord.NotFound:
            await self.bot.db.execute("DELETE FROM starboard_entries WHERE id = $1", entry_id)
            return

        if amount_of_stars < self.star_threshold:
            # Delete starboard message if too few stars
            await old_bot_message.delete()
            await self.bot.db.execute("UPDATE starboard_entries SET starboard_message_id = NULL WHERE id = $1",
                                      entry_id)

        else:
            # Update star amount
            embed = self.get_starboard_embed(message, amount_of_stars)
            await old_bot_message.edit(embed=embed)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        if self.starboard_channel.id != payload.channel_id:
            return

        await self.bot.db.execute("DELETE FROM starboard_entries WHERE starboard_message_id = $1", payload.message_id)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload):
        if self.starboard_channel.id != payload.channel_id:
            return

        messages = list(payload.message_ids)

        await self.bot.db.execute("DELETE FROM starboard_entries WHERE starboard_message_id = ANY($1::bigint[]);",
                                  messages)


def setup(bot):
    bot.add_cog(Starboard(bot))
