import enum
import re
import typing
import discord

from discord.ext import commands
from discord.ext.commands import BadArgument

from bot.config import config
from bot.utils import context, exceptions


class InternalAPIWebhookConverter(commands.Converter):
    @classmethod
    async def convert(cls, ctx, argument):
        if argument.startswith("#"):
            argument = argument[1:]

        if not argument.isdigit():
            return await ctx.send(f"{config.NO} `{argument}` is not a real ID.")

        return int(argument)


class PoliticalPartyJoinMode(enum.Enum):
    PUBLIC = "Public"
    REQUEST = "Request"
    PRIVATE = "Private"


class PoliticalParty(commands.Converter):
    """
    Represents a political party.

    The lookup strategy for the converter is as follows (in order):
        1. Lookup by Discord role ID on the Democraciv guild.
        2. Lookup via database by name/alias.
        3. Lookup via Discord roles on the Democraciv Guild by name/alias.

    """

    def __init__(self, **kwargs):
        self.discord_invite: str = kwargs.get("discord_invite")
        self.aliases: typing.List[str] = kwargs.get("aliases")
        self.join_mode: PoliticalPartyJoinMode = kwargs.get("join_mode")
        self._leaders: typing.List[int] = kwargs.get("leaders")
        self._id: int = kwargs.get("id")
        self._bot = kwargs.get("bot")

        if kwargs.get("role"):
            self._id = kwargs.get("role").id

    @property
    def leaders(self) -> typing.List[typing.Union[discord.Member, discord.User, None]]:
        return [self._bot.dciv.get_member(leader) or self._bot.get_user(leader) for leader in self._leaders]

    @property
    def role(self) -> typing.Optional[discord.Role]:
        return self._bot.dciv.get_role(self._id)

    async def get_logo(self):
        if not self.discord_invite:
            return None

        try:
            invite = await self._bot.fetch_invite(self.discord_invite)
            return invite.guild.icon_url_as(format="png")
        except (discord.NotFound, discord.HTTPException):
            return None

    @classmethod
    async def convert(cls, ctx, argument):
        argument = str(argument)

        try:
            arg_as_int = int(argument)
        except ValueError:
            arg_as_int = 0

        if argument.lower() in (
                "independent",
                "independant",
                "ind",
                "ind.",
                "independents",
                "independants",
        ):
            return cls(
                role=discord.utils.get(ctx.bot.dciv.roles, name="Independent"),
                join_mode=PoliticalPartyJoinMode.PUBLIC,
                bot=ctx.bot,
            )

        party = await ctx.bot.db.fetchrow(
            "SELECT party.id, party.discord_invite, party.join_mode FROM party JOIN party_alias a ON "
            "party.id = a.party_id WHERE a.alias = $1 OR party.id = $2",
            argument.lower(),
            arg_as_int,
        )

        if not party or not ctx.bot.dciv.get_role(party["id"]):
            raise exceptions.PartyNotFoundError(argument)

        aliases = await ctx.bot.db.fetch("SELECT alias FROM party_alias WHERE party_id = $1", party["id"])
        aliases = [record["alias"] for record in aliases]

        leaders = await ctx.bot.db.fetch("SELECT leader_id FROM party_leader WHERE party_id = $1", party["id"])
        leaders = [record["leader_id"] for record in leaders]

        return cls(
            id=party["id"],
            leaders=leaders,
            discord_invite=party["discord_invite"],
            join_mode=PoliticalPartyJoinMode(party["join_mode"]),
            aliases=aliases,
            bot=ctx.bot,
        )


class Selfrole(commands.Converter):
    def __init__(self, **kwargs):
        self._join_message: str = kwargs.get("join_message")
        self._guild = kwargs.get("guild_id")
        self._role = kwargs.get("role_id")
        self._bot = kwargs.get("bot")

    @property
    def join_message(self):
        return self._join_message.replace("✅", "")

    @property
    def guild(self) -> typing.Optional[discord.Guild]:
        return self._bot.get_guild(self._guild)

    @property
    def role(self) -> typing.Optional[discord.Role]:
        if self.guild is not None:
            return self.guild.get_role(self._role)

        return None

    @classmethod
    async def convert(cls, ctx, argument):
        arg = argument.lower()

        def predicate(r):
            return r.name.lower() == arg

        role = discord.utils.find(predicate, ctx.guild.roles)

        if not role:
            raise exceptions.NotFoundError(
                f"{config.NO} There is no selfrole on this server that matches `{argument}`. "
                f"If you're trying to join or leave a political party,"
                f" check `{config.BOT_PREFIX}help Political Parties`"
            )

        role_record = await ctx.bot.db.fetchrow("SELECT * FROM selfrole WHERE guild_id = $1 AND role_id = $2",
                                                ctx.guild.id, role.id)

        if not role_record:
            raise exceptions.NotFoundError(
                f"{config.NO} There is no selfrole on this server that matches `{argument}`. "
                f"If you're trying to join or leave a political party,"
                f" check `{config.BOT_PREFIX}help Political Parties`"
            )

        return cls(**role_record, bot=ctx.bot)


class BanConverter(commands.Converter):
    async def convert(self, ctx, argument):
        member = None

        try:
            member = await CaseInsensitiveMember().convert(ctx, argument)
        except commands.BadArgument:
            id_regex = re.compile(r"([0-9]{15,21})$")
            if id_regex.match(argument):
                member = int(argument)

        if member:
            return member

        raise BadArgument(message=f"{config.NO} I couldn't find that person.")


class UnbanConverter(commands.Converter):
    async def convert(self, ctx, argument):
        user = None

        def find_by_name(ban_entry):
            return ban_entry.user.name.lower() == argument.lower()

        def find_by_id(ban_entry):
            return ban_entry.user.id == argument

        try:
            user = await CaseInsensitiveUser().convert(ctx, argument)
        except commands.BadArgument:
            try:
                argument = int(argument, base=10)
                ban = discord.utils.find(find_by_id, await ctx.guild.bans())
            except ValueError:
                ban = discord.utils.find(find_by_name, await ctx.guild.bans())

            if ban:
                user = ban.user

        if user:
            return user

        raise BadArgument(f"{config.NO} I couldn't find that person.")


class CaseInsensitiveTextChannel(commands.TextChannelConverter):
    async def convert(self, ctx, argument):
        try:
            return await super().convert(ctx, argument)
        except BadArgument:
            arg = argument.lower()

            if arg.startswith("#"):
                arg = arg[1:]

            def predicate(c):
                return c.name.lower() == arg

            channel = discord.utils.find(predicate, ctx.guild.text_channels)

            if channel:
                return channel

            raise BadArgument(f"{config.NO} There is no channel named `{argument}` on this server.")


class CaseInsensitiveTextChannelOrCategoryChannel(CaseInsensitiveTextChannel):
    async def convert(self, ctx, argument):
        try:
            return await super().convert(ctx, argument)
        except BadArgument:
            try:
                return await commands.CategoryChannelConverter().convert(ctx, argument)
            except BadArgument:
                arg = argument.lower()

                if arg.startswith("#"):
                    arg = arg[1:]

                def predicate(c):
                    return c.name.lower() == arg

                channel = discord.utils.find(predicate, ctx.guild.categories)

                if channel:
                    return channel

                raise BadArgument(f"{config.NO} There is no channel or category named `{argument}` on this server.")


class CaseInsensitiveRole(commands.RoleConverter):
    async def convert(self, ctx: context.CustomContext, argument):
        try:
            return await super().convert(ctx, argument)
        except BadArgument:
            arg = argument.lower()

            if arg.startswith("@"):
                arg = arg[1:]

            def predicate(r):
                return r.name.lower() == arg

            role = discord.utils.find(predicate, ctx.guild.roles)

            if role:
                return role

            raise BadArgument(f"{config.NO} There is no role named `{argument}` on this server.")


class DemocracivCaseInsensitiveRole(CaseInsensitiveRole):
    async def convert(self, ctx: context.CustomContext, argument):
        try:
            return await super().convert(ctx, argument)
        except BadArgument:
            arg = argument.lower()

            def predicate(r):
                return r.name.lower() == arg

            role = discord.utils.find(predicate, ctx.bot.dciv.roles)

            if role:
                return role

            raise BadArgument(
                f"{config.NO} There is no role named `{argument}` on this server or the {ctx.bot.dciv.name} server."
            )


class CaseInsensitiveMember(commands.MemberConverter):
    async def convert(self, ctx, argument):
        try:
            return await super().convert(ctx, argument)
        except BadArgument:
            arg = argument.lower()

            def predicate(m):
                return m.name.lower() == arg or (m.nick and m.nick.lower() == arg) or str(m) == arg

            member = discord.utils.find(predicate, ctx.guild.members)

            if member:
                return member

            raise BadArgument(f"{config.NO} I couldn't find that person.")


class CaseInsensitiveUser(commands.UserConverter):
    async def convert(self, ctx, argument):
        try:
            return await super().convert(ctx, argument)
        except BadArgument:
            arg = argument.lower()

            def predicate(m):
                return m.name.lower() == arg or str(m) == arg

            user = discord.utils.find(predicate, ctx.bot.users)

            if user:
                return user

            raise BadArgument(f"{config.NO} I couldn't find that person.")


class Tag(commands.Converter):
    """
    Represents a Tag. Can be global or local.

    The lookup strategy for the converter is as follows (in order):
        1. Lookup through global tags by alias
        2. Lookup through guild tags by alias

    """

    def __init__(self, **kwargs):
        self.id: int = kwargs.get("id")
        self.name: str = kwargs.get("name")
        self.title: str = kwargs.get("title")
        self.content: str = kwargs.get("content")
        self.is_global: bool = kwargs.get("_global")
        self.uses: int = kwargs.get("uses")
        self.aliases: typing.List[str] = kwargs.get("aliases")
        self.is_embedded: bool = kwargs.get("is_embedded")
        self._author: int = kwargs.get("author", None)
        self._guild_id: int = kwargs.get("guild_id")
        self._bot = kwargs.get("bot")
        self.invoked_with: str = kwargs.get("invoked_with", None)

    @property
    def guild(self) -> discord.Guild:
        return self._bot.get_guild(self._guild_id)

    @property
    def author(self) -> typing.Union[discord.Member, discord.User, None]:
        user = None

        if self.guild:
            user = self.guild.get_member(self._author)

        if user is None:
            user = self._bot.get_user(self._author)

        return user

    @property
    def clean_content(self) -> str:
        return discord.utils.escape_mentions(self.content)

    @classmethod
    async def convert(cls, ctx, argument: str):
        sql = """SELECT 
                tag.id, tag.guild_id, tag.name, tag.title, tag.content, tag.global, tag.author, tag.uses, tag.is_embedded
                 FROM tag
                 INNER JOIN
                  tag_lookup look ON look.tag_id = tag.id 
                 WHERE
                  (tag.global = true AND look.alias = $1) 
                 OR
                  (look.alias = $1 AND tag.guild_id = $2)
               """

        guild_id = 0 if not ctx.guild else ctx.guild.id
        tag_record = await ctx.bot.db.fetchrow(sql, argument.lower(), guild_id)

        if tag_record is None:
            raise exceptions.TagError(f"{config.NO} There is no global tag from the {ctx.bot.dciv.name} server nor a "
                                      f"local tag from this server named `{argument}`.")

        aliases = await ctx.bot.db.fetch("SELECT alias FROM tag_lookup WHERE tag_id = $1", tag_record["id"])
        aliases = [record["alias"] for record in aliases]
        return cls(**tag_record, bot=ctx.bot, aliases=aliases, invoked_with=argument.lower())


class OwnedTag(Tag):
    """
    Represents a Tag that the Context.author owns.
    """

    @classmethod
    async def convert(cls, ctx, argument: str):
        tag = await super().convert(ctx, argument)

        if tag.is_global and tag.guild.id != ctx.guild.id:
            raise exceptions.TagError(
                f"{config.NO} Global tags can only be edited, transferred or removed on "
                f"the server they were originally created on."
            )

        if tag.author.id != ctx.author.id or not ctx.author.guild_permissions.administrator:
            raise exceptions.TagError(f"{config.NO} That isn't your tag.")

        return tag
