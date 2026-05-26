import collections
import dataclasses
import enum
import re
import typing

import discord
from discord.utils import escape_markdown

from bot.config import config, mk
from bot.services.context import CommandContextProtocol
from bot.services.results import OperationResult, PageResult
from bot.utils import converter, exceptions


class TagContentType(enum.Enum):
    TEXT = 1
    IMAGE = 2
    INVITE = 3
    CUSTOM_EMOJI = 4
    YOUTUBE_TENOR_GIPHY = 5
    VIDEO = 6
    PARTIAL_IMAGE = 7


@dataclasses.dataclass
class TagStatsRecord:
    name: str
    uses: int


@dataclasses.dataclass
class TagAuthorStats:
    user: discord.User
    amount: int


@dataclasses.dataclass
class TagPersonStats:
    person: typing.Union[discord.Member, discord.User]
    total_tags: int
    local_tags: int
    global_tags: int
    top_local_tags: typing.Sequence[TagStatsRecord]
    top_global_tags: typing.Sequence[TagStatsRecord]


@dataclasses.dataclass
class TagOverviewStats:
    guild_name: str
    guild_icon: typing.Optional[str]
    total_tags: int
    local_tags: int
    global_tags: int
    top_global_tags: typing.Sequence[TagStatsRecord]
    top_server_tags: typing.Sequence[TagStatsRecord]
    top_local_tags: typing.Sequence[TagStatsRecord]
    top_global_tag_creators: typing.Sequence[TagAuthorStats]
    top_server_tag_creators: typing.Sequence[TagAuthorStats]


class TagService:
    def __init__(self, bot):
        self.bot = bot
        self.emoji_pattern = re.compile(
            r"<(?P<animated>a)?:(?P<name>[0-9a-zA-Z_]{2,32}):(?P<id>[0-9]{15,21})>"
        )
        self.discord_invite_pattern = re.compile(
            r"(?:https?://)?discord(?:app\.com/invite|\.gg)/?[a-zA-Z0-9]+/?"
        )
        self.url_pattern = re.compile(
            r"((http|https)\:\/\/)?[a-zA-Z0-9\.\/\?\:@\-_=#]+\.([a-zA-Z]){2,6}([a-zA-Z0-9\.\&\/\?\:@\-_=#])*"
        )

    def normalize_tag_name(self, name: str) -> str:
        name = (name or "").strip()
        if name.startswith(config.BOT_PREFIX):
            name = name[len(config.BOT_PREFIX) :].strip()
        return name.lower()

    async def validate_tag_name(
        self,
        ctx: CommandContextProtocol,
        name: str,
    ) -> str:
        name = self.normalize_tag_name(name)

        if not name:
            raise exceptions.TagError(
                f"{config.NO} The name of your tag or alias cannot be empty."
            )

        if self.bot.get_command(name):
            raise exceptions.TagError(
                f"{config.NO} You can't create a tag or alias with the same name of one of my commands."
            )

        if len(name) > 50:
            raise exceptions.TagError(
                f"{config.NO} The name or alias cannot be longer than 50 characters."
            )

        tags = await self.bot.db.fetch(
            "SELECT tag_lookup.tag_id FROM tag_lookup "
            "JOIN tag t on tag_lookup.tag_id = t.id "
            "WHERE "
            "(t.global = true AND tag_lookup.alias = $1) "
            "OR "
            "(t.guild_id = $2 AND tag_lookup.alias = $1)",
            name,
            ctx.guild.id,
        )
        if tags:
            if ctx.guild.id == self.bot.dciv.id:
                msg = (
                    f"{config.NO} A tag or tag alias from this server with that "
                    "name already exists."
                )
            else:
                msg = (
                    f"{config.NO} A global tag from the {self.bot.dciv.name} "
                    "server with that name, or a local tag or tag alias from "
                    "this server with that name, already exists."
                )
            raise exceptions.TagError(msg)

        return name

    def can_make_global(
        self,
        ctx: CommandContextProtocol,
        *,
        include_owner: bool = False,
    ) -> bool:
        if ctx.guild is None or ctx.guild.id != self.bot.dciv.id:
            return False

        if not isinstance(ctx.author, discord.Member):
            return False

        if ctx.author.guild_permissions.administrator:
            return True

        if include_owner and ctx.author.id == self.bot.owner_id:
            return True

        if self.bot.mk.IS_NATION_BOT:
            try:
                nation_admin = self.bot.get_democraciv_role(
                    mk.DemocracivRole.NATION_ADMIN
                )
            except exceptions.RoleNotFoundError:
                nation_admin = None

            return nation_admin is not None and nation_admin in ctx.author.roles

        return False

    def get_tag_content_type(self, tag_content: str) -> TagContentType:
        url_endings_image = (
            ".jpeg",
            ".jpg",
            ".png",
            ".gif",
            ".webp",
            ".bmp",
            ".img",
            ".svg",
        )
        url_endings_video = (".avi", ".mp4", ".mp3", ".mov", ".flv", ".wmv")

        if self.url_pattern.fullmatch(tag_content) and (
            any(substring in tag_content.lower() for substring in url_endings_image)
        ):
            return TagContentType.IMAGE

        if self.url_pattern.match(tag_content) and (
            any(substring in tag_content.lower() for substring in url_endings_image)
        ):
            return TagContentType.PARTIAL_IMAGE

        if self.url_pattern.match(tag_content) and (
            any(substring in tag_content.lower() for substring in url_endings_video)
        ):
            return TagContentType.VIDEO

        if any(
            substring in tag_content
            for substring in ["youtube", "youtu.be", "tenor.com", "gph.is", "giphy.com"]
        ):
            return TagContentType.YOUTUBE_TENOR_GIPHY

        if self.emoji_pattern.fullmatch(tag_content):
            return TagContentType.CUSTOM_EMOJI

        if self.discord_invite_pattern.match(tag_content):
            return TagContentType.INVITE

        return TagContentType.TEXT

    async def list_tags(self, ctx: CommandContextProtocol) -> PageResult:
        entries = []
        global_tags = await self.bot.db.fetch(
            "SELECT * FROM tag WHERE global = true ORDER BY uses desc"
        )

        if global_tags:
            entries.append(
                f"### Global Tags\n-# Tags can only be made global by {self.bot.dciv.name} "
                "Moderation and Nation Admins. Global tags work in every server I am in, "
                "as well as in DMs with me.\n"
            )
            entries.extend(
                f"* `{config.BOT_PREFIX}{record['name']}`  {escape_markdown(record['title'])}"
                for record in global_tags
            )

        if ctx.guild:
            local_tags = await self.bot.db.fetch(
                "SELECT * FROM tag WHERE guild_id = $1 AND global = false"
                " ORDER BY uses desc",
                ctx.guild.id,
            )

            if local_tags:
                entries.append(
                    f"\n\n### Local Tags\n-# Every Tag that was not explicitly made global by "
                    f"{self.bot.dciv.name} Moderation or a Nation Admin is a local tag, "
                    "and only works in the server it was made in.\n"
                )
                entries.extend(
                    f"* `{config.BOT_PREFIX}{record['name']}`  {escape_markdown(record['title'])}"
                    for record in local_tags
                )

            author = f"All Tags in {ctx.guild.name}"
            icon = ctx.guild_icon
            empty_message = "There are no tags on this server."
        else:
            author = "All Global Tags"
            icon = self.bot.user.display_avatar.url
            empty_message = "There are no global tags yet."

        if len(entries) < 2:
            entries = []

        return PageResult(
            entries=entries,
            author=author,
            icon=icon,
            empty_message=empty_message,
            per_page=12,
        )

    async def list_local_tags(self, ctx: CommandContextProtocol) -> PageResult:
        records = await self.bot.db.fetch(
            "SELECT * FROM tag WHERE guild_id = $1 AND global = false "
            "ORDER BY uses desc",
            ctx.guild.id,
        )
        return PageResult(
            entries=[
                f"* `{config.BOT_PREFIX}{record['name']}`  {escape_markdown(record['title'])}"
                for record in records
            ],
            author=f"Local Tags in {ctx.guild.name}",
            icon=ctx.guild_icon,
            empty_message="There are no local tags on this server.",
            per_page=12,
        )

    async def list_tags_from_member(
        self,
        ctx: CommandContextProtocol,
        member: typing.Union[discord.Member, discord.User],
    ) -> PageResult:
        records = await self.bot.db.fetch(
            "SELECT * FROM tag WHERE author = $1 AND guild_id = $2 ORDER BY uses desc",
            member.id,
            ctx.guild.id,
        )
        return PageResult(
            entries=[
                f"`{config.BOT_PREFIX}{record['name']}`  {escape_markdown(record['title'])}"
                for record in records
            ],
            author=f"Tags from {member.display_name}",
            icon=member.display_avatar.url,
            empty_message=f"{member} hasn't made any tags on this server yet.",
            per_page=12,
        )

    async def search_tags(self, ctx: CommandContextProtocol, query: str) -> PageResult:
        records = await self.bot.db.fetch(
            """SELECT tag.name, tag.title FROM tag
               JOIN tag_lookup l on l.tag_id = tag.id
               WHERE (tag.global = true OR tag.guild_id = $2)
               AND (lower(l.alias) % $1 OR lower(l.alias) LIKE '%' || $1 || '%' OR lower(tag.title) LIKE '%' || $1 || '%'
                   OR lower(tag.content) LIKE '%' || $1 || '%')
               ORDER BY similarity(l.alias, $1) DESC
               LIMIT 20""",
            query.lower(),
            ctx.guild.id if ctx.guild else 0,
        )
        pretty_names = {}
        for record in records:
            pretty_names[
                f"`{config.BOT_PREFIX}{record['name']}`  {escape_markdown(record['title'])}"
            ] = None

        icon = self.bot.user.display_avatar.url if not ctx.guild else ctx.guild_icon
        return PageResult(
            entries=list(pretty_names),
            author=f"Tags matching '{query}'",
            icon=icon,
            empty_message="Nothing found.",
            per_page=12,
        )

    async def get_random_tag_name(
        self, ctx: CommandContextProtocol
    ) -> typing.Optional[str]:
        return await self.bot.db.fetchval(
            "SELECT name FROM tag WHERE tag.global = true OR tag.guild_id = $1 ORDER BY random() limit 1",
            ctx.guild.id if ctx.guild else 0,
        )

    async def create_tag(
        self,
        ctx: CommandContextProtocol,
        *,
        name: str,
        title: str,
        content: str,
        is_embedded: bool,
        is_global: bool,
        allow_owner_global: bool = False,
    ) -> OperationResult:
        name = await self.validate_tag_name(ctx, name)
        self._validate_tag_title_and_content(title=title, content=content)

        if is_global and not self.can_make_global(
            ctx, include_owner=allow_owner_global
        ):
            raise exceptions.TagError(
                f"{config.NO} Only {self.bot.dciv.name} Moderators and Nation Admins can make global tags."
            )

        async with self.bot.db.acquire() as con:
            async with con.transaction():
                tag_id = await con.fetchval(
                    "INSERT INTO tag (guild_id, name, content, title,"
                    " global, author, is_embedded) VALUES "
                    "($1, $2, $3, $4, $5, $6, $7) RETURNING id",
                    ctx.guild.id,
                    name,
                    content,
                    title,
                    is_global,
                    ctx.author.id,
                    is_embedded,
                )
                await con.execute(
                    "INSERT INTO tag_lookup (tag_id, alias) VALUES ($1, $2)",
                    tag_id,
                    name,
                )

        return OperationResult(
            message=(
                f"{config.YES} The `{config.BOT_PREFIX}{name}` tag was added.\n"
                f"{config.HINT} You can add other people as collaborators for this tag, "
                "so that they can edit and add & remove aliases, with "
                f"`{config.BOT_PREFIX}tag share {name}`."
            )
        )

    async def edit_tag(
        self,
        ctx: CommandContextProtocol,
        *,
        tag: converter.Tag,
        title: str,
        content: str,
        is_embedded: bool,
        is_global: bool,
        allow_owner_global: bool = False,
    ) -> OperationResult:
        self._validate_tag_title_and_content(title=title, content=content)

        if is_global != tag.is_global and not self.can_make_global(
            ctx, include_owner=allow_owner_global
        ):
            raise exceptions.TagError(
                f"{config.NO} Only {self.bot.dciv.name} Moderators and Nation Admins can change global tag status."
            )

        await self.bot.db.execute(
            "UPDATE tag SET content = $1, title = $3, is_embedded = $4, global = $5 WHERE id = $2",
            content,
            tag.id,
            title,
            is_embedded,
            is_global,
        )
        return OperationResult(
            message=(
                f"{config.YES} The tag was edited.\n{config.HINT} You can add "
                "other people as collaborators for this tag, so that they can "
                "edit and add & remove aliases, with "
                f"`{config.BOT_PREFIX}tag share {tag.name}`."
            )
        )

    async def add_alias(
        self,
        ctx: CommandContextProtocol,
        *,
        tag: converter.Tag,
        alias: str,
    ) -> OperationResult:
        alias = await self.validate_tag_name(ctx, alias)
        await self.bot.db.execute(
            "INSERT INTO tag_lookup (alias, tag_id) VALUES ($1, $2)",
            alias,
            tag.id,
        )
        return OperationResult(
            message=(
                f"{config.YES} The `{config.BOT_PREFIX}{alias}` alias was added to "
                f"`{config.BOT_PREFIX}{tag.name}`."
                f"\n{config.HINT} You can add other people as collaborators for this tag, "
                "so that they can edit and add & remove aliases, with "
                f"`{config.BOT_PREFIX}tag share {tag.name}`."
            )
        )

    async def remove_alias(
        self,
        *,
        alias: converter.Tag,
    ) -> OperationResult:
        if alias.invoked_with == alias.name:
            raise exceptions.TagError(
                f"{config.NO} That is not an alias, but the tag's name. "
                f"Try `{config.BOT_PREFIX}tag delete {alias.invoked_with}` instead."
            )

        await self.bot.db.execute(
            "DELETE FROM tag_lookup WHERE alias = $1 AND tag_id = $2",
            alias.invoked_with,
            alias.id,
        )
        return OperationResult(
            message=(
                f"{config.YES} The alias `{config.BOT_PREFIX}{alias.invoked_with}` "
                f"from `{config.BOT_PREFIX}{alias.name}` was removed."
                f"\n{config.HINT} You can add other people as collaborators for this tag, "
                "so that they can edit and add & remove aliases, with "
                f"`{config.BOT_PREFIX}tag share {alias.name}`."
            )
        )

    async def delete_tag(
        self,
        ctx: CommandContextProtocol,
        *,
        tag: converter.Tag,
    ) -> OperationResult:
        async with self.bot.db.acquire() as con:
            async with con.transaction():
                await con.execute("DELETE FROM tag_lookup WHERE tag_id = $1", tag.id)
                await con.execute(
                    "DELETE FROM tag WHERE name = $1 AND guild_id = $2",
                    tag.name,
                    ctx.guild.id,
                )

        return OperationResult(
            message=f"{config.YES} `{config.BOT_PREFIX}{tag.name}` was removed."
        )

    async def claim_tag(
        self,
        ctx: CommandContextProtocol,
        *,
        tag: converter.Tag,
    ) -> OperationResult:
        if tag.is_global:
            raise exceptions.TagError(f"{config.NO} Global tags cannot be claimed.")

        if tag.author == ctx.author:
            raise exceptions.TagError(f"{config.NO} You already own this tag.")

        if isinstance(tag.author, discord.Member):
            raise exceptions.TagError(
                f"{config.NO} The owner of this tag is still in this server."
            )

        await self.bot.db.execute(
            "UPDATE tag SET author = $1 WHERE id = $2", ctx.author.id, tag.id
        )
        return OperationResult(
            message=(
                f"{config.YES} You are now the owner `{config.BOT_PREFIX}{tag.name}`."
            )
        )

    async def transfer_tag(
        self,
        ctx: CommandContextProtocol,
        *,
        tag: converter.Tag,
        to_person: typing.Union[discord.Member, discord.User],
    ) -> OperationResult:
        if to_person.id == ctx.author.id:
            raise exceptions.TagError(
                f"{config.NO} You cannot transfer your tag to yourself."
            )

        await self.bot.db.execute(
            "UPDATE tag SET author = $1 WHERE id = $2",
            to_person.id,
            tag.id,
        )
        return OperationResult(
            message=(
                f"{config.YES} {to_person} is now the owner of "
                f"`{config.BOT_PREFIX}{tag.name}`."
            )
        )

    async def update_collaborators(
        self,
        *,
        tag: converter.Tag,
        people: typing.Sequence[discord.Member],
        add: bool,
    ) -> OperationResult:
        if not people:
            raise exceptions.TagError(
                f"{config.NO} Something went wrong, you didn't specify anybody."
            )

        people = [
            person
            for person in people
            if not getattr(person, "bot", False) and person.id != tag.author_id
        ]
        if not people:
            raise exceptions.TagError(
                f"{config.NO} No valid collaborators were specified."
            )

        for person in people:
            if add:
                await self.bot.db.execute(
                    "INSERT INTO tag_collaborator (tag_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    tag.id,
                    person.id,
                )
            else:
                await self.bot.db.execute(
                    "DELETE FROM tag_collaborator WHERE tag_id = $1 AND user_id = $2",
                    tag.id,
                    person.id,
                )

        action = "can now edit" if add else "can __no longer__ edit"
        return OperationResult(
            message=(
                f"{config.YES} Those people {action} your "
                f"`{config.BOT_PREFIX}{tag.name}` tag."
            )
        )

    async def toggle_global_tag(self, *, tag: converter.Tag) -> OperationResult:
        if not tag.is_global:
            await self.bot.db.execute(
                "UPDATE tag SET global = true WHERE id = $1", tag.id
            )
            return OperationResult(
                message=(
                    f"{config.YES} `{config.BOT_PREFIX}{tag.name}` is now a global tag."
                )
            )

        await self.bot.db.execute("UPDATE tag SET global = false WHERE id = $1", tag.id)
        return OperationResult(
            message=(
                f"{config.YES} `{config.BOT_PREFIX}{tag.name}` is no longer a global tag."
            )
        )

    async def get_person_stats(
        self,
        ctx: CommandContextProtocol,
        person: typing.Union[discord.Member, discord.User],
    ) -> TagPersonStats:
        amount = await self.bot.db.fetch(
            "SELECT COUNT(name) FROM tag WHERE author = $1 "
            "UNION ALL "
            "SELECT COUNT(name) FROM tag WHERE author = $1 AND guild_id = $2 "
            "UNION ALL "
            "SELECT COUNT(name) FROM tag WHERE author = $1 AND global = true ",
            person.id,
            ctx.guild.id,
        )
        top_tags = await self.bot.db.fetch(
            "SELECT name, uses FROM tag WHERE author = $1 AND guild_id = $2 "
            "ORDER BY uses DESC LIMIT 5",
            person.id,
            ctx.guild.id,
        )
        top_global_tags = await self.bot.db.fetch(
            "SELECT name, uses FROM tag WHERE author = $1 AND global = true "
            "ORDER BY uses DESC LIMIT 5",
            person.id,
        )

        return TagPersonStats(
            person=person,
            total_tags=amount[0]["count"],
            local_tags=amount[1]["count"],
            global_tags=amount[2]["count"],
            top_local_tags=self._tag_stats_records(top_tags),
            top_global_tags=self._tag_stats_records(top_global_tags),
        )

    async def get_overview_stats(
        self,
        ctx: CommandContextProtocol,
    ) -> TagOverviewStats:
        total = await self.bot.db.fetch(
            "SELECT COUNT(name) FROM tag "
            "UNION ALL "
            "SELECT COUNT(name) FROM tag WHERE guild_id = $1 "
            "UNION ALL "
            "SELECT COUNT(name) FROM tag WHERE global = true",
            ctx.guild.id,
        )
        top_global_tags = await self.bot.db.fetch(
            "SELECT name, uses FROM tag WHERE global = true "
            "ORDER BY uses DESC LIMIT 5"
        )
        top_server_tags = await self.bot.db.fetch(
            "SELECT name, uses FROM tag WHERE guild_id = $1 "
            "ORDER BY uses DESC LIMIT 5",
            ctx.guild.id,
        )
        top_local_tags = await self.bot.db.fetch(
            "SELECT name, uses FROM tag WHERE global = false AND guild_id = $1 "
            "ORDER BY uses DESC LIMIT 5",
            ctx.guild.id,
        )
        top_tag_creators = await self.bot.db.fetch(
            "SELECT author FROM tag WHERE guild_id = $1", ctx.guild.id
        )
        top_global_tag_creators = await self.bot.db.fetch(
            "SELECT author FROM tag WHERE global = true"
        )

        return TagOverviewStats(
            guild_name=ctx.guild.name,
            guild_icon=ctx.guild_icon,
            total_tags=total[0]["count"],
            local_tags=total[1]["count"],
            global_tags=total[2]["count"],
            top_global_tags=self._tag_stats_records(top_global_tags),
            top_server_tags=self._tag_stats_records(top_server_tags),
            top_local_tags=self._tag_stats_records(top_local_tags),
            top_global_tag_creators=self._author_stats_records(top_global_tag_creators),
            top_server_tag_creators=self._author_stats_records(top_tag_creators),
        )

    def _validate_tag_title_and_content(self, *, title: str, content: str):
        if len(title) > 256:
            raise exceptions.TagError(
                f"{config.NO} The title cannot be longer than 256 characters."
            )

        if len(content) > 2000:
            raise exceptions.TagError(
                f"{config.NO} The content cannot be longer than 2000 characters."
            )

    @staticmethod
    def _tag_stats_records(records) -> typing.List[TagStatsRecord]:
        return [
            TagStatsRecord(name=record["name"], uses=record["uses"])
            for record in records
        ]

    def _author_stats_records(self, records) -> typing.List[TagAuthorStats]:
        counter = collections.Counter(record["author"] for record in records)
        stats = []

        for user_id, amount in counter.most_common(5):
            user = self.bot.get_user(user_id)
            if user is not None:
                stats.append(TagAuthorStats(user=user, amount=amount))

        return stats
