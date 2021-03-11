import enum
import re
import typing
import discord

from discord.ext import commands
from discord.ext.commands import BadArgument
from fuzzywuzzy import process

from bot.config import config, mk
from bot.utils import context, exceptions
from utils import text


class InternalAPIWebhookConverter(commands.Converter):
    model = "notification ID"

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
        self.aliases: typing.List[str] = kwargs.get("aliases", [])
        self.join_mode: PoliticalPartyJoinMode = kwargs.get("join_mode")
        self._leaders: typing.List[int] = kwargs.get("leaders", [])
        self._id: int = kwargs.get("id")
        self._bot = kwargs.get("bot")
        self.is_independent = kwargs.get("ind", False)

    @property
    def leaders(self) -> typing.List[typing.Union[discord.Member, discord.User]]:
        return list(
            filter(None, [self._bot.dciv.get_member(leader) or self._bot.get_user(leader) for leader in self._leaders])
        )

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
            ind_role = discord.utils.get(ctx.bot.dciv.roles, name="Independent")

            if ind_role:
                return cls(
                    id=ind_role.id,
                    join_mode=PoliticalPartyJoinMode.PUBLIC,
                    bot=ctx.bot,
                    ind=True,
                )

        party = await ctx.bot.db.fetchrow(
            "SELECT party.id, party.discord_invite, party.join_mode FROM party JOIN party_alias a ON "
            "party.id = a.party_id WHERE a.alias = $1 OR party.id = $2",
            argument.lower(),
            arg_as_int,
        )

        if not party or not ctx.bot.dciv.get_role(party["id"]):
            parties = await ctx.bot.db.fetch("SELECT id FROM party")
            parties = [record["id"] for record in parties]
            msg = []

            for party in parties:
                role = ctx.bot.dciv.get_role(party)
                if role is not None:
                    msg.append(f"`{role.name}`")

            if msg:
                msg = ", ".join(msg)
                message = (
                    f"{config.NO} There is no political party that matches `{argument}`.\n"
                    f"{config.HINT} Try one of these: {msg}"
                )
            else:
                message = f"{config.NO} There is no political party that matches `{argument}`."

            raise exceptions.NotFoundError(message)

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
                f"{config.NO} There is no selfrole on this server that matches `{argument}`.\n"
                f"{config.HINT} If you're trying to join or leave a political party,"
                f" check `{config.BOT_PREFIX}help party`"
            )

        role_record = await ctx.bot.db.fetchrow(
            "SELECT * FROM selfrole WHERE guild_id = $1 AND role_id = $2", ctx.guild.id, role.id
        )

        if not role_record:
            raise exceptions.NotFoundError(
                f"{config.NO} There is no selfrole on this server that matches `{argument}`.\n"
                f"{config.HINT} If you're trying to join or leave a political party, "
                f"check `{config.BOT_PREFIX}help party`"
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
            bans = await ctx.guild.bans()
            try:
                argument = int(argument, base=10)
                ban = discord.utils.find(find_by_id, bans)
            except ValueError:
                ban = discord.utils.find(find_by_name, bans)

            if ban:
                user = ban.user

        if user:
            return user

        raise BadArgument(f"{config.NO} I couldn't find that person.")


async def fuzzy_search(ctx, arg, iterable, model):
    match = process.extract(arg, iterable, limit=5)

    menu = text.FuzzyChoose(question=f"Which {model} did you mean?", choices=[mtch for mtch, _ in match])
    return await menu.prompt(ctx)


class CaseInsensitiveTextChannel(commands.TextChannelConverter):
    model = "channel"

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


class CaseInsensitiveCategoryChannel(commands.CategoryChannelConverter):
    model = "category"

    async def convert(self, ctx, argument):
        try:
            return await super().convert(ctx, argument)
        except BadArgument:
            arg = argument.lower()

            if arg.startswith("#"):
                arg = arg[1:]

            def predicate(c):
                return c.name.lower() == arg

            channel = discord.utils.find(predicate, ctx.guild.categories)

            if channel:
                return channel

            raise BadArgument(f"{config.NO} There is no category named `{argument}` on this server.")


class CaseInsensitiveTextChannelOrCategoryChannel(CaseInsensitiveTextChannel):
    model = "channel or category"

    async def convert(self, ctx, argument):
        try:
            return await super().convert(ctx, argument)
        except BadArgument:
            try:
                return await CaseInsensitiveCategoryChannel().convert(ctx, argument)
            except BadArgument:
                raise BadArgument(f"{config.NO} There is no channel or category named `{argument}` on this server.")


class CaseInsensitiveRole(commands.RoleConverter):
    model = "role"

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


def find_dciv_role(ctx, argument):
    def predicate(r):
        return r.name.lower() == argument

    return discord.utils.find(predicate, ctx.bot.dciv.roles)


class DemocracivCaseInsensitiveRole(CaseInsensitiveRole):
    async def convert(self, ctx: context.CustomContext, argument):
        try:
            return await super().convert(ctx, argument)
        except BadArgument as e:
            if ctx.guild.id == ctx.bot.dciv.id:
                raise e

            arg = argument.lower()

            role = find_dciv_role(ctx, arg)

            if role:
                return role

            """for nation_prefix in ["canada - ", "rome - ", "maori - ", "ottoman - "]:
                if arg.startswith(nation_prefix):
                    nation_arg = arg

                elif arg.startswith(nation_prefix[:-2]):
                    nation_arg = arg.replace(nation_prefix[:-2], nation_prefix)

                else:
                    nation_arg = f"{nation_prefix}{arg}"

                role = find_dciv_role(ctx, nation_arg)

                if role:
                    return role"""

            raise BadArgument(
                f"{config.NO} There is no role named `{argument}` on this " f"server or the {ctx.bot.dciv.name} server."
            )


class FuzzyCIRole(commands.Converter):
    async def convert(self, ctx: context.CustomContext, argument):
        roles = [role.name for role in ctx.guild.roles]
        role_name = await fuzzy_search(ctx, argument, roles, "role")

        if not role_name:
            raise BadArgument(f"{config.NO} There is no role named `{argument}` on this " f"server")

        role = discord.utils.get(ctx.guild.roles, name=role_name)

        if role:
            return role

        raise BadArgument(f"{config.NO} There is no role named `{argument}` on this " f"server")


class FuzzyDemocracivCIRole(commands.Converter):
    async def convert(self, ctx: context.CustomContext, argument):
        if ctx.guild.id == ctx.bot.dciv.id:
            return await FuzzyCIRole().convert(ctx, argument)

        roles = [role.name for role in ctx.guild.roles]
        roles.extend([f"{role.name} - *{ctx.bot.dciv} Role*" for role in ctx.bot.dciv.roles])
        role_name = await fuzzy_search(ctx, argument, roles, "role")

        if not role_name:
            raise BadArgument(
                f"{config.NO} There is no role named `{argument}` on this " f"server or the {ctx.bot.dciv.name} server."
            )

        role = discord.utils.get(ctx.guild.roles, name=role_name)

        if role:
            return role

        role = discord.utils.get(ctx.bot.dciv.roles, name=role_name)

        if role:
            return role

        raise BadArgument(
            f"{config.NO} There is no role named `{argument}` on this " f"server or the {ctx.bot.dciv.name} server."
        )


class CaseInsensitiveMember(commands.MemberConverter):
    model = "person"

    async def convert(self, ctx, argument):
        try:
            return await super().convert(ctx, argument)
        except BadArgument:
            arg = argument.lower()

            def predicate(m):
                return m.name.lower() == arg or (m.nick and m.nick.lower() == arg) or str(m).lower() == arg

            member = discord.utils.find(predicate, ctx.guild.members)

            if member:
                return member

            raise BadArgument(f"{config.NO} I couldn't find that person.")


class FuzzyCIMember(commands.Converter):
    async def convert(self, ctx, argument):
        # todo - make this not bad

        members = {}
        all_tries = []

        for member in ctx.guild.members:
            all_tries.append(member.name)

            if member.nick:
                members[member.nick] = member.id
                all_tries.append(member.nick)

            members[member.name] = member.id

        match = process.extract(argument, all_tries, limit=10)

        fmt = {}

        for m, _ in match:
            person = ctx.guild.get_member(members[m])
            fmt[person] = None

        fmt = list(fmt.keys())[:5]

        menu = text.FuzzyChoose(question=f"Who did you mean?", choices=fmt)
        result = await menu.prompt(ctx)

        if result:
            return result

        raise BadArgument(f"{config.NO} I couldn't find that person.")


class CaseInsensitiveUser(commands.UserConverter):
    model = "person"

    async def convert(self, ctx, argument):
        try:
            return await super().convert(ctx, argument)
        except BadArgument:
            arg = argument.lower()

            def predicate(m):
                return m.name.lower() == arg or str(m).lower() == arg

            user = discord.utils.find(predicate, ctx.bot.users)

            if user:
                return user

            raise BadArgument(f"{config.NO} I couldn't find that person.")


class CIMemberOrCIRole(DemocracivCaseInsensitiveRole):
    async def convert(self, ctx: context.CustomContext, argument):
        try:
            return await super().convert(ctx, argument)
        except BadArgument:
            return await CaseInsensitiveMember().convert(ctx, argument)


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
        self.is_global: bool = kwargs.get("global")
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
            if ctx.guild and ctx.guild.id != ctx.bot.dciv.id:
                msg = f"{config.NO} There is no global tag from the {ctx.bot.dciv.name} server nor a local tag from this server named `{argument}`."
            elif ctx.guild and ctx.guild.id == ctx.bot.dciv.id:
                msg = f"{config.NO} There is no tag from this server named `{argument}`."
            else:
                msg = f"{config.NO} There is no global tag from the {ctx.bot.dciv.name} server named `{argument}`."

            raise exceptions.TagError(msg)

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

        if ctx.bot.mk.IS_NATION_BOT:
            try:
                nation_admin = ctx.bot.get_democraciv_role(mk.DemocracivRole.NATION_ADMIN)

                if nation_admin in ctx.author.roles:
                    return tag
            except exceptions.RoleNotFoundError:
                pass

        if (tag.author and tag.author.id == ctx.author.id) or ctx.author.guild_permissions.administrator or ctx.author.id == ctx.bot.owner_id:
            return tag

        raise exceptions.TagError(f"{config.NO} That isn't your tag.")
