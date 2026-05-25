import typing

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import config
from bot.slash import context as slash_context
from bot.utils import text


class StarboardSlash(commands.Cog):
    starboard = app_commands.Group(
        name="starboard",
        description="Show Starboard statistics.",
        guild_only=True,
    )

    def __init__(self, bot):
        self.bot = bot

    @property
    def starboard_channel(self) -> typing.Optional[discord.TextChannel]:
        return self.bot.dciv.get_channel(config.STARBOARD_CHANNEL)

    @staticmethod
    def records_to_value(records, fmt=None, default="-"):
        if not records:
            return default

        emoji = 0x1F947
        fmt = fmt or (lambda value: value)
        return "\n".join(
            f'{chr(emoji + index)} {fmt(record["ID"])} ({record["Stars"]} stars)'
            for index, record in enumerate(records)
        )

    @starboard.command(
        name="overview", description="Show general Starboard statistics."
    )
    async def overview(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="starboard overview",
        )
        await ctx.defer()

        total_starred_messages = await self.bot.db.fetchval(
            "SELECT COUNT(*) FROM starboard_entry"
        )
        total_stars = await self.bot.db.fetchval(
            "SELECT COUNT(*) FROM starboard_starrer INNER JOIN starboard_entry "
            "entry ON entry.id = starboard_starrer.entry_id;"
        )

        query = """WITH t AS (
                       SELECT
                           entry.author_id AS entry_author_id,
                           starboard_starrer.starrer_id,
                           entry.starboard_message_id
                       FROM starboard_starrer
                       INNER JOIN starboard_entry entry
                       ON entry.id = starboard_starrer.entry_id
                   )
                   (
                       SELECT t.entry_author_id AS "ID", 1 AS "Type", COUNT(*) AS "Stars"
                       FROM t
                       WHERE t.entry_author_id IS NOT NULL
                       GROUP BY t.entry_author_id
                       ORDER BY "Stars" DESC
                       LIMIT 3
                   )
                   UNION ALL
                   (
                       SELECT t.starrer_id AS "ID", 2 AS "Type", COUNT(*) AS "Stars"
                       FROM t
                       GROUP BY t.starrer_id
                       ORDER BY "Stars" DESC
                       LIMIT 3
                   )
                   UNION ALL
                   (
                       SELECT t.starboard_message_id AS "ID", 3 AS "Type", COUNT(*) AS "Stars"
                       FROM t
                       WHERE t.starboard_message_id IS NOT NULL
                       GROUP BY t.starboard_message_id
                       ORDER BY "Stars" DESC
                       LIMIT 3
                   );"""

        records = await self.bot.db.fetch(query)

        embed = text.SafeEmbed(
            title="Starboard Stats",
            description=f"So far, there are {total_starred_messages} messages starred"
            f" with a total of {total_stars} stars.",
            colour=0xFFAC33,
        )

        starred_posts = [r for r in records if r["Type"] == 3]
        starred_posts_with_link = []

        for post in starred_posts:
            record = await self.bot.db.fetchval(
                "SELECT message_jump_url FROM starboard_entry "
                "WHERE starboard_message_id = $1",
                post["ID"],
            )
            starred_posts_with_link.append(
                {"ID": f"[Jump to Message]({record})", "Stars": post["Stars"]}
            )

        embed.add_field(
            name="Top Starred Messages",
            value=self.records_to_value(starred_posts_with_link),
            inline=False,
        )

        to_mention = lambda o: f"<@{o}>"

        star_receivers = [r for r in records if r["Type"] == 1]
        value = self.records_to_value(star_receivers, to_mention, default="No one!")
        embed.add_field(name="Top Star Receivers", value=value, inline=False)

        star_givers = [r for r in records if r["Type"] == 2]
        value = self.records_to_value(star_givers, to_mention, default="No one!")
        embed.add_field(name="Top Star Givers", value=value, inline=False)

        if self.starboard_channel is not None:
            embed.set_footer(
                text="Collecting stars since",
                icon_url="https://cdn.discordapp.com/attachments/"
                "639549494693724170/679824104190115911/star.png",
            )
            embed.timestamp = self.starboard_channel.created_at
        await ctx.send(embed=embed)

    @starboard.command(
        name="person", description="Show Starboard stats for one person."
    )
    async def member(self, interaction: discord.Interaction, member: discord.Member):
        ctx = slash_context.from_interaction(
            interaction, command_name="starboard person"
        )
        await ctx.defer()

        embed = text.SafeEmbed(colour=0xFFAC33)
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)

        stars_received = await self.bot.db.fetchval(
            """SELECT COUNT(*)
               FROM starboard_starrer
               INNER JOIN starboard_entry entry
               ON entry.id=starboard_starrer.entry_id
               WHERE entry.author_id=$1;""",
            member.id,
        )
        stars_given = await self.bot.db.fetchval(
            """SELECT COUNT(*)
               FROM starboard_starrer
               INNER JOIN starboard_entry entry
               ON entry.id=starboard_starrer.entry_id
               WHERE starboard_starrer.starrer_id=$1;""",
            member.id,
        )
        top_three_starred = await self.bot.db.fetch(
            """SELECT starboard_entry.message_jump_url, COUNT(*) AS "stars"
               FROM starboard_starrer
               INNER JOIN starboard_entry
               ON starboard_entry.id=starboard_starrer.entry_id
               WHERE starboard_entry.author_id=$1
               GROUP BY starboard_entry.message_jump_url
               ORDER BY "stars" DESC
               LIMIT 3;""",
            member.id,
        )

        top_three_starred_fmt = []

        for record in top_three_starred:
            top_three_starred_fmt.append(
                {
                    "ID": f"[Jump to Message]({record['message_jump_url']})",
                    "Stars": record["stars"],
                }
            )

        messages_starred = await self.bot.db.fetchval(
            "SELECT COUNT(*) FROM starboard_entry WHERE starboard_message_id IS NOT NULL AND author_id = $1;",
            member.id,
        )

        embed.add_field(
            name="Messages on the Starboard", value=messages_starred, inline=False
        )
        embed.add_field(name="Stars Received", value=stars_received, inline=True)
        embed.add_field(name="Stars Given", value=stars_given, inline=True)
        embed.add_field(
            name="Top Starred Messages",
            value=self.records_to_value(top_three_starred_fmt),
            inline=False,
        )
        await ctx.send(embed=embed)


async def setup(bot):
    if config.STARBOARD_ENABLED:
        await bot.add_cog(StarboardSlash(bot))
