from __future__ import annotations

import collections
import enum
import itertools
import re
import typing
import discord

from discord.ext import commands
from discord.ext.commands import BadArgument
from fuzzywuzzy import process
from typing import TypeVar

from bot.config import config, mk
from bot.utils import context, exceptions, text

T = TypeVar("T")

ConvertersWithWeights = collections.namedtuple(
    "ConvertersWithWeights", ["converter", "weight"]
)


class _Fuzzy(commands.Converter):
    def __init__(
        self,
        converter: typing.List[ConvertersWithWeights] = None,
        settings: FuzzySettings = None,
    ):
        self.converter = converter
        self.settings = settings

    def __call__(self, *args, **kwargs):
        return self

    def __getitem__(self, converter: typing.Union[typing.Tuple[T], T]) -> Fuzzy[T]:
        if not isinstance(converter, tuple):
            converter = (converter,)

        settings = None

        for thing in converter:
            if isinstance(thing, FuzzySettings):
                settings = thing

        convs = []
        for i, conv in enumerate(converter):
            if isinstance(conv, FuzzySettings):
                continue

            weight = settings.get_weight(i) if settings else None
            convs.append(ConvertersWithWeights(conv(), weight))

        return self.__class__(converter=convs, settings=settings)

    async def convert(self, ctx, argument) -> T:
        exception_mapping = {}

        for converter, _ in self.converter:
            if isinstance(converter, commands.Converter) or hasattr(
                converter, "convert"
            ):
                try:
                    return await converter.convert(ctx, argument)
                except Exception as e:
                    exception_mapping[converter] = e
                    continue
            else:
                try:
                    return converter(argument)
                except Exception as e:
                    exception_mapping[converter] = e
                    continue

        sources: typing.Dict[
            str, typing.Dict[typing.Any, None]
        ] = collections.defaultdict(dict)
        model = []
        description = []

        for converter, weight in self.converter:
            if not hasattr(converter, "get_fuzzy_source"):
                continue

            source = await converter.get_fuzzy_source(ctx, argument)
            group = getattr(converter, "model", "Other")

            for thing in source[:weight]:
                sources[group][thing] = None

            if source and converter.model not in model:
                model.append(converter.model)

            if source and converter.fuzzy_description:
                description.append(converter.fuzzy_description)

        if hasattr(exception_mapping[self.converter[0].converter], "message"):
            first_exception = exception_mapping[self.converter[0].converter].message
        else:
            first_exception = str(exception_mapping[self.converter[0][0]])

        exception = (
            self.settings.no_choice_exception
            if self.settings and self.settings.no_choice_exception
            else first_exception
        )

        if not sources:
            raise commands.BadArgument(exception)

        if len(model) > 1:
            first = ", ".join(model[:-1])
            fmt = f"{first} or {model[-1]}"
            menu_cls = text.FuzzyMultiModelChoose
        else:
            fmt = model[0]
            menu_cls = text.FuzzyChoose

        kwargs = {
            "question": f"Which {fmt} did you mean?",
            "description": "\n".join(description),
            "choices": list(
                itertools.chain.from_iterable(list(s.keys()) for s in sources.values())
            ),
        }

        if len(model) > 1:
            kwargs["models"] = sources

        menu = menu_cls(ctx, **kwargs)
        result = await menu.prompt()

        if result:
            return result

        raise commands.BadArgument(exception)


Fuzzy = _Fuzzy()


class FuzzyableMixin:
    model: str
    fuzzy_description: typing.Optional[str] = None

    async def get_fuzzy_source(
        self, ctx: context.CustomContext, argument: str
    ) -> typing.Iterable:
        """This must return an Iterable of the _already converted_, final objects.

        The __str__ of each object will be shown in the FuzzyChoose menu for the user to choose."""
        raise NotImplementedError()


class FuzzySettings:
    def __init__(
        self,
        *,
        no_choice_exception: typing.Optional[str] = None,
        weights: typing.Optional[typing.Sequence[int]] = None,
        embed_description: typing.Optional[str] = None,
    ):
        self.no_choice_exception = no_choice_exception
        self.weights = weights
        self.embed_description = embed_description

    def __call__(self, *args, **kwargs):
        return

    def get_weight(self, index: int) -> typing.Optional[int]:
        if self.weights:
            try:
                return self.weights[index]
            except IndexError:
                return None


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


class PoliticalParty(commands.Converter, FuzzyableMixin):
    """
    Represents a political party.

    The lookup strategy for the converter is as follows (in order):
        1. Lookup by Discord role ID on the Democraciv guild.
        2. Lookup via database by name/alias.
        3. Lookup via Discord roles on the Democraciv Guild by name/alias.

    """

    model = "Political Party"

    def __init__(self, **kwargs):
        self.discord_invite: str = kwargs.get("discord_invite")
        self.aliases: typing.List[str] = kwargs.get("aliases", [])
        self.join_mode: PoliticalPartyJoinMode = kwargs.get("join_mode")
        self.leader_ids: typing.List[int] = kwargs.get("leaders", [])
        self._id: int = kwargs.get("id")
        self._bot = kwargs.get("bot")
        self.is_independent = kwargs.get("ind", False)

    def __str__(self):
        return self.role.name if self.role else "*Deleted Party"

    def __eq__(self, other):
        return isinstance(other, PoliticalParty) and other._id == self._id

    def __hash__(self):
        return hash(self._id)

    async def get_fuzzy_source(self, ctx, argument):
        arg = argument.lower()
        lookup = {}

        possibilities = await ctx.bot.db.fetch(
            "SELECT party_id, alias FROM party_alias"
        )
        for record in possibilities:
            lookup[record["alias"].title()] = record["party_id"]

        possibilities = [r["alias"].title() for r in possibilities]
        match = process.extract(arg, possibilities, limit=10)
        fmt = {}

        for m, _ in match:
            try:
                party = await PoliticalParty.convert(ctx, lookup[m])
                fmt[party] = None
            except Exception:
                # sanity check
                continue

        fmt = list(fmt.keys())[:5]
        return fmt

    @property
    def leaders(self) -> typing.List[typing.Union[discord.Member, discord.User]]:
        return list(
            filter(
                None,
                [
                    self._bot.dciv.get_member(leader) or self._bot.get_user(leader)
                    for leader in self.leader_ids
                ],
            )
        )

    @property
    def role(self) -> typing.Optional[discord.Role]:
        return self._bot.dciv.get_role(self._id)

    async def get_logo(self):
        if not self.discord_invite:
            return None

        try:
            invite = await self._bot.fetch_invite(self.discord_invite)
            return invite.guild.icon.url
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
            raise exceptions.NotFoundError(
                f"{config.NO} There is no political party that matches `{argument}`.\n"
                f"{config.HINT} Try one of the ones in `{config.BOT_PREFIX}parties`."
            )

        aliases = await ctx.bot.db.fetch(
            "SELECT alias FROM party_alias WHERE party_id = $1", party["id"]
        )
        aliases = [record["alias"] for record in aliases]

        leaders = await ctx.bot.db.fetch(
            "SELECT leader_id FROM party_leader WHERE party_id = $1", party["id"]
        )
        leaders = [record["leader_id"] for record in leaders]

        return cls(
            id=party["id"],
            leaders=leaders,
            discord_invite=party["discord_invite"],
            join_mode=PoliticalPartyJoinMode(party["join_mode"]),
            aliases=aliases,
            bot=ctx.bot,
        )


class Selfrole(commands.Converter, FuzzyableMixin):
    class MockRole:
        id = 0
        name = mention = "*Deleted Role*"
        members = []

        def __bool__(self):
            return False

        def __str__(self):
            return self.name

        async def delete(self):
            pass

    model = "Selfrole"

    def __init__(self, **kwargs):
        self._join_message: str = kwargs.get("join_message")
        self._guild = kwargs.get("guild_id")
        self._role = kwargs.get("role_id")
        self._bot = kwargs.get("bot")

    def __str__(self):
        return self.role.name

    @property
    def join_message(self):
        return self._join_message.replace("✅", "")

    @property
    def guild(self) -> typing.Optional[discord.Guild]:
        return self._bot.get_guild(self._guild)

    @property
    def role(self) -> typing.Union[discord.Role, MockRole]:
        if self.guild is not None:
            return self.guild.get_role(self._role)

        return self.MockRole()

    async def get_fuzzy_source(
        self, ctx: context.CustomContext, argument: str
    ) -> typing.Iterable:
        available_roles = await ctx.bot.db.fetch(
            "SELECT * FROM selfrole WHERE guild_id = $1", ctx.guild.id
        )
        roles = {}

        for record in available_roles:
            role = ctx.guild.get_role(record["role_id"])

            if role:
                roles[role.name] = Selfrole(**dict(record), bot=ctx.bot)

        match = process.extract(
            argument, [r.role.name for r in roles.values()], limit=5
        )
        fmt = []

        for m, _ in match:
            fmt.append(roles[m])

        return fmt

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
            "SELECT * FROM selfrole WHERE guild_id = $1 AND role_id = $2",
            ctx.guild.id,
            role.id,
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


def _find_channel(arg, what):
    if arg.startswith("#"):
        arg = arg[1:]

    def predicate(c):
        return c.name.lower() == arg

    return discord.utils.find(predicate, what)


class CaseInsensitiveTextChannel(commands.TextChannelConverter, FuzzyableMixin):
    model = "Channel"

    async def get_fuzzy_source(
        self, ctx: context.CustomContext, argument: str
    ) -> typing.Iterable:
        channel = {channel.id: channel.name for channel in ctx.guild.text_channels}
        match = process.extract(argument, channel, limit=5)

        fmt = []

        for m, _, k in match:
            fmt.append(ctx.guild.get_channel(k))

        return fmt

    async def convert(self, ctx, argument):
        try:
            return await super().convert(ctx, argument)
        except BadArgument:
            channel = _find_channel(argument.lower(), ctx.guild.text_channels)

            if channel:
                return channel

            raise BadArgument(
                f"{config.NO} There is no channel named `{argument}` on this server."
            )


class CaseInsensitiveCategoryChannel(commands.CategoryChannelConverter, FuzzyableMixin):
    model = "Category"

    async def get_fuzzy_source(
        self, ctx: context.CustomContext, argument: str
    ) -> typing.Iterable:
        categories = {category.id: category.name for category in ctx.guild.categories}
        match = process.extract(argument, categories, limit=5)

        fmt = []

        for m, _, k in match:
            fmt.append(ctx.guild.get_channel(k))

        return fmt

    async def convert(self, ctx, argument):
        try:
            return await super().convert(ctx, argument)
        except BadArgument:
            channel = _find_channel(argument.lower(), ctx.guild.categories)

            if channel:
                return channel

            raise BadArgument(
                f"{config.NO} There is no category named `{argument}` on this server."
            )


class CaseInsensitiveRole(commands.RoleConverter, FuzzyableMixin):
    model = "Role"

    async def get_fuzzy_source(
        self, ctx: context.CustomContext, argument: str
    ) -> typing.Iterable:
        roles = [role.name for role in ctx.guild.roles]

        match = process.extract(argument, roles, limit=5)
        fmt = []
        for m, _ in match:
            fmt.append(discord.utils.get(ctx.guild.roles, name=m))

        return fmt

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

            raise BadArgument(
                f"{config.NO} There is no role named `{argument}` on this server."
            )


class DemocracivCaseInsensitiveRole(commands.Converter, FuzzyableMixin):
    """If used in Fuzzy context, should be used together with the CaseInsensitiveRole converter."""

    model = "Role from the Democraciv Server"

    async def get_fuzzy_source(
        self, ctx: context.CustomContext, argument: str
    ) -> typing.Iterable:
        if ctx.guild.id == ctx.bot.dciv.id:
            return []

        new_ctx = context.MockContext(bot=ctx.bot, guild=ctx.bot.dciv)
        return await CaseInsensitiveRole().get_fuzzy_source(new_ctx, argument)

    async def convert(self, ctx: context.CustomContext, argument):
        if ctx.guild.id == ctx.bot.dciv.id:
            return await CaseInsensitiveRole().convert(ctx, argument)

        new_ctx = context.MockContext(bot=ctx.bot, guild=ctx.bot.dciv)

        try:
            return await CaseInsensitiveRole().convert(new_ctx, argument)
        except BadArgument:
            raise BadArgument(
                f"{config.NO} There is no role named `{argument}` on the {ctx.bot.dciv.name} server."
            )

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


class CaseInsensitiveMember(commands.MemberConverter, FuzzyableMixin):
    model = "Person"

    async def get_fuzzy_source(
        self, ctx: context.CustomContext, argument: str
    ) -> typing.Iterable:
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

        return list(fmt.keys())[:5]

    async def convert(self, ctx, argument):
        try:
            return await super().convert(ctx, argument)
        except BadArgument:
            arg = argument.lower()

            def predicate(m):
                return (
                    m.name.lower() == arg
                    or (m.nick and m.nick.lower() == arg)
                    or str(m).lower() == arg
                )

            member = discord.utils.find(predicate, ctx.guild.members)

            if member:
                return member

            raise BadArgument(f"{config.NO} I couldn't find that person.")


class CaseInsensitiveUser(commands.UserConverter, FuzzyableMixin):
    model = "Person"

    async def get_fuzzy_source(
        self, ctx: context.CustomContext, argument: str
    ) -> typing.Iterable:
        users = {user.id: user.name for user in ctx.bot.users}
        match = process.extract(argument, users, limit=5)

        fmt = []

        for m, _, k in match:
            fmt.append(ctx.bot.get_user(k))

        return fmt

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


class Tag(commands.Converter, FuzzyableMixin):
    """
    Represents a Tag.

    The lookup strategy for the converter is as follows (in order):
        1. Lookup through global tags by alias
        2. Lookup through guild tags by alias

    """

    model = "Tag"

    def __hash__(self):
        return hash(self.id)

    def __str__(self):
        return f"`{config.BOT_PREFIX}{self.name}`"

    def __init__(self, **kwargs):
        self.id: int = kwargs.get("id")
        self.name: str = kwargs.get("name")
        self.title: str = kwargs.get("title")
        self.content: str = kwargs.get("content")
        self.is_global: bool = kwargs.get("global")
        self.uses: int = kwargs.get("uses")
        self.aliases: typing.List[str] = kwargs.get("aliases", [])
        self.is_embedded: bool = kwargs.get("is_embedded")
        self.author_id: int = kwargs.get("author")
        self.guild_id: int = kwargs.get("guild_id")
        self._bot = kwargs.get("bot")
        self.invoked_with: str = kwargs.get("invoked_with")
        self.collaborator_ids: typing.List[int] = kwargs.get("collaborators", [])

    @property
    def guild(self) -> discord.Guild:
        return self._bot.get_guild(self.guild_id)

    @property
    def collaborators(self) -> typing.List[typing.Union[discord.Member, discord.User]]:
        return list(
            filter(
                None,
                [
                    self.guild.get_member(collaborator)
                    or self._bot.get_user(collaborator)
                    for collaborator in self.collaborator_ids
                ],
            )
        )

    @property
    def author(self) -> typing.Union[discord.Member, discord.User, None]:
        user = None

        if self.guild:
            user = self.guild.get_member(self.author_id)

        if user is None:
            user = self._bot.get_user(self.author_id)

        return user

    @property
    def clean_content(self) -> str:
        return discord.utils.escape_mentions(self.content)

    async def get_fuzzy_source(
        self, ctx: context.CustomContext, argument: str
    ) -> typing.Iterable:
        lowered = argument.lower()

        sql = """SELECT 
                    tag.id, tag.guild_id, tag.name, tag.title, tag.content, tag.global, tag.author, tag.uses, tag.is_embedded
                     FROM tag
                     INNER JOIN
                      tag_lookup look ON look.tag_id = tag.id 
                     WHERE
                       (look.alias % $1 OR lower(look.alias) LIKE '%' || $1 || '%')
                     AND
                      (tag.global = true OR tag.guild_id = $2)
                     ORDER BY similarity(lower(name), $1) DESC LIMIT 5;
                   """

        matches = await ctx.bot.db.fetch(sql, lowered, ctx.guild.id)
        found = {}

        for match in matches:
            aliases = await ctx.bot.db.fetch(
                "SELECT alias FROM tag_lookup WHERE tag_id = $1", match["id"]
            )
            aliases = [record["alias"] for record in aliases]

            collaborators = await ctx.bot.db.fetch(
                "SELECT user_id FROM tag_collaborator WHERE tag_id = $1", match["id"]
            )
            collaborators = [record["user_id"] for record in collaborators]

            tag = Tag(
                **match,
                bot=ctx.bot,
                aliases=aliases,
                invoked_with=lowered,
                collaborators=collaborators,
            )
            found[tag] = None

        return list(found.keys())

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
                msg = (
                    f"{config.NO} There is no tag from this server named `{argument}`."
                )
            else:
                msg = f"{config.NO} There is no global tag from the {ctx.bot.dciv.name} server named `{argument}`."

            raise exceptions.TagError(msg)

        aliases = await ctx.bot.db.fetch(
            "SELECT alias FROM tag_lookup WHERE tag_id = $1", tag_record["id"]
        )
        aliases = [record["alias"] for record in aliases]

        collaborators = await ctx.bot.db.fetch(
            "SELECT user_id FROM tag_collaborator WHERE tag_id = $1", tag_record["id"]
        )
        collaborators = [record["user_id"] for record in collaborators]

        return cls(
            **tag_record,
            bot=ctx.bot,
            aliases=aliases,
            invoked_with=argument.lower(),
            collaborators=collaborators,
        )


class CollaboratorOfTag(Tag):
    """
    Represents a Tag that the Context.author either owns, or is a collaborator of.
    """

    def _is_allowed(self, ctx, tag: Tag) -> bool:
        if tag.author_id == ctx.author.id or ctx.author.id in tag.collaborator_ids:
            return True

        if ctx.bot.mk.IS_NATION_BOT:
            try:
                nation_admin = ctx.bot.get_democraciv_role(
                    mk.DemocracivRole.NATION_ADMIN
                )

                if nation_admin in ctx.author.roles:
                    return True
            except exceptions.RoleNotFoundError:
                pass

        if (
            ctx.author.guild_permissions.administrator
            or ctx.author.id == ctx.bot.owner_id
        ):
            return True

        return False

    async def get_fuzzy_source(
        self, ctx: context.CustomContext, argument: str
    ) -> typing.Iterable:
        matches = await super().get_fuzzy_source(ctx, argument)
        return [m for m in matches if self._is_allowed(ctx, m)]

    async def convert(self, ctx, argument: str):
        tag = await super().convert(ctx, argument)

        if self._is_allowed(ctx, tag):
            return tag

        raise exceptions.TagError(
            f"{config.NO} That isn't your tag, and the tag's owner "
            f"hasn't made you a collaborator."
        )


class OwnedTag(Tag):
    """
    Represents a Tag that the Context.author owns.
    """

    def _is_allowed(self, ctx, tag: Tag) -> bool:
        if tag.is_global and tag.guild_id != ctx.guild.id:
            return False

        if ctx.bot.mk.IS_NATION_BOT:
            try:
                nation_admin = ctx.bot.get_democraciv_role(
                    mk.DemocracivRole.NATION_ADMIN
                )

                if nation_admin in ctx.author.roles:
                    return True
            except exceptions.RoleNotFoundError:
                pass

        if (
            (tag.author_id == ctx.author.id)
            or ctx.author.guild_permissions.administrator
            or ctx.author.id == ctx.bot.owner_id
        ):
            return True

        return False

    async def get_fuzzy_source(
        self, ctx: context.CustomContext, argument: str
    ) -> typing.Iterable:
        matches = await super().get_fuzzy_source(ctx, argument)
        return [m for m in matches if self._is_allowed(ctx, m)]

    async def convert(self, ctx, argument: str):
        tag = await super().convert(ctx, argument)

        if tag.is_global and tag.guild.id != ctx.guild.id:
            raise exceptions.TagError(
                f"{config.NO} Global tags can only be edited, transferred or removed on "
                f"the server they were originally created on."
            )

        if self._is_allowed(ctx, tag):
            return tag

        raise exceptions.TagError(f"{config.NO} That isn't your tag.")
