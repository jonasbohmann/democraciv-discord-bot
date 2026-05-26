import dataclasses
import typing

import discord

from bot.config import config


@dataclasses.dataclass
class StarboardRecord:
    id: typing.Any
    stars: int


@dataclasses.dataclass
class StarboardOverview:
    total_starred_messages: int
    total_stars: int
    top_starred_messages: typing.List[StarboardRecord]
    top_star_receivers: typing.List[StarboardRecord]
    top_star_givers: typing.List[StarboardRecord]
    starboard_channel: typing.Optional[discord.TextChannel]


@dataclasses.dataclass
class StarboardMemberStats:
    member: typing.Union[discord.Member, discord.User]
    messages_starred: int
    stars_received: int
    stars_given: int
    top_starred_messages: typing.List[StarboardRecord]


class StarboardService:
    def __init__(self, bot):
        self.bot = bot

    @property
    def starboard_channel(self) -> typing.Optional[discord.TextChannel]:
        return self.bot.dciv.get_channel(config.STARBOARD_CHANNEL)

    async def get_overview(self) -> StarboardOverview:
        total_starred_messages = await self.bot.db.fetchval(
            "SELECT COUNT(*) FROM starboard_entry"
        )
        total_stars = await self.bot.db.fetchval(
            "SELECT COUNT(*) FROM starboard_starrer INNER JOIN starboard_entry "
            "entry ON entry.id = starboard_starrer.entry_id;"
        )

        # Fetches top 3 starred posts, star receivers, and star givers.
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

        top_starred_messages = []
        for post in [record for record in records if record["Type"] == 3]:
            jump_url = await self.bot.db.fetchval(
                "SELECT message_jump_url FROM starboard_entry "
                "WHERE starboard_message_id = $1",
                post["ID"],
            )
            top_starred_messages.append(
                StarboardRecord(
                    id=f"[Jump to Message]({jump_url})", stars=post["Stars"]
                )
            )

        return StarboardOverview(
            total_starred_messages=total_starred_messages,
            total_stars=total_stars,
            top_starred_messages=top_starred_messages,
            top_star_receivers=[
                StarboardRecord(id=record["ID"], stars=record["Stars"])
                for record in records
                if record["Type"] == 1
            ],
            top_star_givers=[
                StarboardRecord(id=record["ID"], stars=record["Stars"])
                for record in records
                if record["Type"] == 2
            ],
            starboard_channel=self.starboard_channel,
        )

    async def get_member_stats(
        self, member: typing.Union[discord.Member, discord.User]
    ) -> StarboardMemberStats:
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
            "SELECT COUNT(*) FROM starboard_entry "
            "WHERE starboard_message_id IS NOT NULL AND author_id = $1;",
            member.id,
        )

        return StarboardMemberStats(
            member=member,
            messages_starred=messages_starred,
            stars_received=stars_received,
            stars_given=stars_given,
            top_starred_messages=[
                StarboardRecord(
                    id=f"[Jump to Message]({record['message_jump_url']})",
                    stars=record["stars"],
                )
                for record in top_three_starred
            ],
        )
