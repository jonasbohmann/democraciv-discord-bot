import discord
from discord import app_commands
from discord.ext import commands

from bot.config import config
from bot.slash import context as slash_context
from bot.slash import ui


class StarboardSlash(commands.Cog):
    starboard = app_commands.Group(
        name="starboard",
        description="Show Starboard statistics.",
        guild_only=True,
    )

    def __init__(self, bot):
        self.bot = bot

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
        starred_posts = [record for record in records if record["Type"] == 3]
        starred_posts_with_link = []

        for post in starred_posts:
            jump_url = await self.bot.db.fetchval(
                "SELECT message_jump_url FROM starboard_entry "
                "WHERE starboard_message_id = $1",
                post["ID"],
            )
            starred_posts_with_link.append(
                {"ID": f"[Jump to Message]({jump_url})", "Stars": post["Stars"]}
            )

        mention = lambda user_id: f"<@{user_id}>"
        sections = [
            ui.LayoutSection(
                "Summary",
                f"So far, there are {total_starred_messages} messages starred with a total of {total_stars} stars.",
            ),
            ui.LayoutSection(
                "Top Starred Messages",
                self.records_to_value(starred_posts_with_link),
            ),
            ui.LayoutSection(
                "Top Star Receivers",
                self.records_to_value(
                    [record for record in records if record["Type"] == 1],
                    mention,
                    default="No one!",
                ),
            ),
            ui.LayoutSection(
                "Top Star Givers",
                self.records_to_value(
                    [record for record in records if record["Type"] == 2],
                    mention,
                    default="No one!",
                ),
            ),
        ]

        await ui.send_static(
            ctx,
            title="Starboard Stats",
            sections=sections,
            title_emoji="\U00002b50",
        )

    @starboard.command(
        name="member", description="Show Starboard stats for one member."
    )
    async def member(self, interaction: discord.Interaction, member: discord.Member):
        ctx = slash_context.from_interaction(
            interaction, command_name="starboard member"
        )
        await ctx.defer()

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
        messages_starred = await self.bot.db.fetchval(
            "SELECT COUNT(*) FROM starboard_entry WHERE starboard_message_id IS NOT NULL AND author_id = $1;",
            member.id,
        )

        top_three_starred_fmt = [
            {
                "ID": f"[Jump to Message]({record['message_jump_url']})",
                "Stars": record["stars"],
            }
            for record in top_three_starred
        ]

        await ui.send_static(
            ctx,
            title=member.display_name,
            title_emoji="\U00002b50",
            sections=[
                ui.LayoutSection("Messages on the Starboard", str(messages_starred)),
                ui.LayoutSection(
                    "Stars",
                    f"Received: {stars_received}\nGiven: {stars_given}",
                ),
                ui.LayoutSection(
                    "Top Starred Messages",
                    self.records_to_value(top_three_starred_fmt),
                ),
            ],
        )


async def setup(bot):
    if config.STARBOARD_ENABLED:
        await bot.add_cog(StarboardSlash(bot))
