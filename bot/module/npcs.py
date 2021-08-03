import typing
import asyncpg
import discord
import collections

from discord.ext import commands
from fuzzywuzzy import process
from lru import LRU

from bot.config import config
from bot.utils.context import CustomContext, CustomCog
from bot.utils import text, converter, paginator
from bot.utils.converter import FuzzyableMixin, Fuzzy, FuzzySettings

NPCPrefixSuffix = collections.namedtuple(
    "NPCPrefixSuffix", ["npc_id", "prefix", "suffix"]
)


class MockOwner:
    mention = "*Person left*"

    def __str__(self):
        return self.mention


class NPCConverter(commands.Converter, FuzzyableMixin):
    """Represents an NPC that the ctx.author owns"""

    model = "NPC"

    def __init__(self, **kwargs):
        self.id: int = kwargs.get("id")
        self.name: str = kwargs.get("name")
        self.avatar_url: str = kwargs.get("avatar_url")
        self.trigger_phrase: str = kwargs.get("trigger_phrase")
        self.owner_id: int = kwargs.get("owner_id")
        self._bot = kwargs.get("bot")

    def __str__(self):
        return self.name

    def __hash__(self):
        return hash(self.id)

    async def get_fuzzy_source(self, ctx, argument: str) -> typing.Iterable:
        npc_cog = ctx.bot.get_cog("NPC")
        try:
            npc_cache = npc_cog._npc_access_cache[ctx.author.id]
        except KeyError:
            return []

        npcs = {
            npc_id: npc_cog._npc_cache[npc_id]["name"]
            for npc_id in npc_cache
            if npc_cog._npc_cache[npc_id]["owner_id"] == ctx.author.id
        }
        return fuzzy_get_npc(ctx, argument, npcs)

    @property
    def owner(self) -> typing.Union[discord.Member, discord.User, MockOwner]:
        person = self._bot.dciv.get_member(self.owner_id) or self._bot.get_user(
            self.owner_id
        )
        return person if person else MockOwner()

    @classmethod
    async def convert(cls, ctx, argument):
        arg = argument.lower()
        try_id = arg

        if arg.startswith("#"):
            try_id = arg[1:]

        try:
            arg_id = int(try_id)
        except ValueError:
            arg_id = -1

        match = await ctx.bot.db.fetchrow(
            "SELECT * FROM npc WHERE (lower(name) = $1 OR id = $2) AND owner_id = $3",
            arg,
            arg_id,
            ctx.author.id,
        )

        if match:
            return cls(**match, bot=ctx.bot)

        raise commands.BadArgument(
            f"{config.NO} You don't have an NPC that matches `{argument}`."
        )


class AnyNPCConverter(NPCConverter):
    async def get_fuzzy_source(self, ctx, argument: str) -> typing.Iterable:
        npc_cache = ctx.bot.get_cog("NPC")._npc_cache
        npcs = {npc["id"]: npc["name"] for npc in npc_cache.values()}
        return fuzzy_get_npc(ctx, argument, npcs)

    @classmethod
    async def convert(cls, ctx, argument):
        arg = argument.lower()

        sql = """SELECT npc.id, npc.name, npc.avatar_url, npc.owner_id, npc.trigger_phrase FROM npc 
            WHERE (lower(npc.name) = $1 OR npc.id = $2)"""

        try_id = arg

        if arg.startswith("#"):
            try_id = arg[1:]

        try:
            arg_id = int(try_id)
        except ValueError:
            arg_id = -1

        match = await ctx.bot.db.fetchrow(sql, arg, arg_id)

        if match:
            return cls(**match, bot=ctx.bot)

        raise commands.BadArgument(
            f"{config.NO} There is no NPC that matches `{argument}`."
        )


def fuzzy_get_npc(ctx, arg, iterable):
    match = process.extract(arg, iterable, limit=5)

    if not match:
        return []

    fmt = {}

    for value, _, key in match:
        npc_obj = NPCConverter(**ctx.bot.get_cog("NPC")._npc_cache[key], bot=ctx.bot)
        fmt[npc_obj] = None

    return list(fmt.keys())[:5]


class AccessToNPCConverter(NPCConverter):
    async def get_fuzzy_source(self, ctx, argument: str) -> typing.Iterable:
        npc_cog = ctx.bot.get_cog("NPC")

        try:
            npc_cache = npc_cog._npc_access_cache[ctx.author.id]
        except KeyError:
            raise []

        npcs = {npc_id: npc_cog._npc_cache[npc_id]["name"] for npc_id in npc_cache}
        return fuzzy_get_npc(ctx, argument, npcs)

    @classmethod
    async def convert(cls, ctx, argument):
        try:
            return await super().convert(ctx, argument)
        except commands.BadArgument:
            arg = argument.lower()

            sql = """SELECT npc.id, npc.name, npc.avatar_url, npc.owner_id, npc.trigger_phrase FROM npc 
                    INNER JOIN npc_allowed_user allowed ON allowed.npc_id = npc.id 
                    WHERE allowed.user_id = $1 AND (lower(npc.name) = $2 OR npc.id = $3)"""

            try_id = arg

            if arg.startswith("#"):
                try_id = arg[1:]

            try:
                arg_id = int(try_id)
            except ValueError:
                arg_id = -1

            match = await ctx.bot.db.fetchrow(sql, ctx.author.id, arg, arg_id)

            if match:
                return cls(**match, bot=ctx.bot)

            raise commands.BadArgument(
                f"{config.NO} You don't have access to an NPC that matches `{argument}`."
            )


class NPC(CustomCog):
    """NPCs can be used to write messages as someone else, for example as an role-played character, or on behalf on an organization or group."""

    def __init__(self, bot):
        super().__init__(bot)
        # channel_id -> webhook url
        self._webhook_cache: typing.Dict[int, str] = {}

        # npc id -> npc
        self._npc_cache: typing.Dict[int, typing.Dict] = {}

        # user_id -> set of NPC ids that user has access to
        self._npc_access_cache: typing.Dict[
            int, typing.Set[int]
        ] = collections.defaultdict(set)

        # user id -> {channel_id -> npc_id}
        self._automatic_npc_cache: typing.Dict[
            int, typing.Dict[int, int]
        ] = collections.defaultdict(dict)

        # channel id -> {message id -> real author id}
        # self._recent_npc_messages = collections.defaultdict(dict)
        self._recent_npc_messages = collections.defaultdict(lambda: LRU(size=100))

        self.bot.loop.create_task(self._load_webhook_cache())
        self.bot.loop.create_task(self._load_npc_cache())
        self.bot.loop.create_task(self._load_automatic_trigger_cache())

    async def _get_default_webhook_avatar(self) -> bytes:
        try:
            return self._default_webhook_avatar
        except AttributeError:
            async with self.bot.session.get(
                "https://cdn.discordapp.com/avatars/487345900239323147/79c38314283392c7e21bab76f77e09e9.png"
            ) as resp:
                self._default_webhook_avatar = avatar = await resp.read()
                return avatar

    async def _load_webhook_cache(self):
        await self.bot.wait_until_ready()

        webhooks = await self.bot.db.fetch(
            "SELECT channel_id, webhook_id, webhook_token FROM npc_webhook"
        )

        for record in webhooks:
            webhook_url = f"https://discord.com/api/webhooks/{record['webhook_id']}/{record['webhook_token']}"
            self._webhook_cache[record["channel_id"]] = webhook_url

    async def _load_npc_cache(self):
        await self.bot.wait_until_ready()

        npcs = await self.bot.db.fetch(
            "SELECT npc.id, npc.name, npc.avatar_url, npc.owner_id, npc.trigger_phrase FROM npc"
        )

        self._npc_cache.clear()
        self._npc_access_cache.clear()

        for record in npcs:
            self._npc_cache[record["id"]] = dict(record)
            self._npc_access_cache[record["owner_id"]].add(record["id"])

            others = await self.bot.db.fetch(
                "SELECT user_id FROM npc_allowed_user WHERE npc_id = $1", record["id"]
            )

            for other in others:
                self._npc_access_cache[other["user_id"]].add(record["id"])

    async def _load_automatic_trigger_cache(self):
        await self.bot.wait_until_ready()

        npcs = await self.bot.db.fetch("SELECT * FROM npc_automatic_mode")

        self._automatic_npc_cache.clear()

        for record in npcs:
            self._automatic_npc_cache[record["user_id"]][record["channel_id"]] = record[
                "npc_id"
            ]

    async def _make_new_webhook(self, channel: discord.TextChannel):
        try:
            webhook: discord.Webhook = await channel.create_webhook(
                name="NPC Hook", avatar=await self._get_default_webhook_avatar()
            )

            await self.bot.db.execute(
                "INSERT INTO npc_webhook (guild_id, channel_id, webhook_id, "
                "webhook_token) VALUES ($1, $2, $3, $4)",
                channel.guild.id,
                channel.id,
                webhook.id,
                webhook.token,
            )

            self._webhook_cache[channel.id] = webhook.url
            return webhook.url
        except discord.HTTPException:
            return None

    async def _get_webhook(self, channel: discord.TextChannel):
        try:
            return self._webhook_cache[channel.id]
        except KeyError:
            webhook = await self._make_new_webhook(channel)

            if webhook:
                return webhook

    @commands.group(
        name="npc", aliases=["npcs"], invoke_without_command=True, case_insensitive=True
    )
    async def npc(self, ctx: CustomContext, *, npc: str = ""):
        """What is an NPC?"""

        if ctx.invoked_with.lower() == "npcs":
            if npc:
                conv = Fuzzy[
                    converter.CaseInsensitiveMember,
                    converter.CaseInsensitiveUser,
                    FuzzySettings(weights=(5, 1)),
                ]
                person = await conv.convert(ctx, npc)

            else:
                person = ctx.author

            return await ctx.invoke(self.bot.get_command("npc list"), person=person)

        if npc:
            converted = await Fuzzy[AnyNPCConverter].convert(ctx, npc)
            return await ctx.invoke(self.bot.get_command("npc info"), npc=converted)

        p = config.BOT_PREFIX
        embed = text.SafeEmbed(
            description=f"NPCs allow you to make it look like you speak as a different character, "
            f"or on behalf of someone else, like an organization or group.\n\n"
            f"This can elevate the role-playing experience by making it clear "
            f"when someone talks in character, or out-of-character (OOC). "
            f"Political parties, newspapers, government departments or other groups can "
            f"use this to release official looking announcements.\n\n"
            f"To get started, you can create a new NPC with `{p}npc create`. NPCs are "
            f"not bound to any server, every NPC that you make on this server can "
            f"also be used in every other server I am in.\n\nServer administrators "
            f"can disable NPC usage on their server for any reason with "
            f"the `{p}server npc` command.\n\n\nSee `{p}help npcs` or "
            f"`{p}commands` to see every NPC-related command and learn more about them."
        )

        embed.set_author(
            name="What are NPCs?",
            icon_url=self.bot.dciv.icon.url
        )
        embed.set_image(
            url="https://cdn.discordapp.com/attachments/818226072805179392/818230819835215882/npc.gif"
        )
        await ctx.send(embed=embed)

    async def _make_avatar(self, ctx):
        avatar_url = None

        if ctx.message.attachments:
            file = ctx.message.attachments[0]
            if file.url.lower().endswith(("png", "jpeg", "jpg", "gif", "webp")):
                avatar_url = file.url

        if not avatar_url:
            avatar = await ctx.input(
                f"{config.USER_INTERACTION_REQUIRED} Reply with a link to the avatar of your NPC."
                f"\n{config.HINT} This should be a valid URL ending with either `.png`, "
                f"`.jpeg`, `.jpg`, `.gif` or `.webp`.\n{config.HINT} You can also just upload the "
                f"avatar image here instead of replying with an URL.\n{config.HINT} If you don't "
                f"want your NPC to have an avatar, just reply with gibberish.",
                image_allowed=True,
            )

            if avatar.lower().startswith("http") and avatar.lower().endswith(
                ("png", "jpeg", "jpg", "gif", "webp")
            ):
                avatar_url = avatar

        return avatar_url

    async def _make_trigger_phrase(self, ctx, *, edit=False, old_phrase=""):
        bot_prefixes = ", ".join(
            [f"`{pref}`" for pref in config.BOT_ADDITIONAL_PREFIXES]
        )

        msg = (
            f"{config.USER_INTERACTION_REQUIRED} How would you like to trigger your NPC? "
            f"Reply with the word `text` surrounded by a prefix __and__/__or__ suffix of your choice."
            f"\n{config.HINT} For example, if you reply with `<<text`, you would write "
            f"`<<Hello!` to make your NPC say `Hello!`."
            f"\n{config.HINT} The trigger phrase will be "
            f"case-insensitive, but it cannot start with any of my bot prefixes: {bot_prefixes}"
        )

        if edit:
            msg = f"{msg}\n{config.HINT} The current trigger phrase is `{old_phrase}`."

        trigger_phrase = await ctx.input(msg)
        trigger_phrase = trigger_phrase.lower()

        if trigger_phrase == "text":
            await ctx.send(
                f"{config.NO} You have to surround the word `text` with a prefix and/or a suffix. "
                f"For example, making the trigger phrase `<<text` would "
                f"mean you had to write `<<Hello!` to make your NPC say `Hello!`."
            )
            return

        if trigger_phrase.startswith(tuple(config.BOT_ADDITIONAL_PREFIXES)):
            await ctx.send(
                f"{config.NO} Your trigger phrase can't have any of "
                f"my bot prefixes at the beginning."
            )
            return

        if "text" not in trigger_phrase:
            await ctx.send(
                f"{config.NO} You have to reply with the word `text` surrounded with a prefix and/or "
                f"a suffix. For example, making the trigger phrase `<<text` would mean "
                f"you had to write `<<Hello!` to make your NPC say `Hello!`."
            )
            return

        prefix, suffix = trigger_phrase.split("text")

        if not prefix and not suffix:
            await ctx.send(
                f"{config.NO} You have to surround the word `text` with a prefix and/or a suffix. "
                f"For example, making the trigger phrase `<<text` would "
                f"mean you had to write `<<Hello!` to make your NPC say `Hello!`."
            )
            return

        return trigger_phrase

    @npc.command(name="create", aliases=["make", "add"])
    async def add_npc(self, ctx: CustomContext, *, name=None):
        """Create a new NPC with a name, avatar and a trigger phrase that will be used to let you speak as that NPC

        Upload an image in the same message as this command to make me use that as your NPC's avatar.

        You can give me the name of your new NPC directly when invoking this command. If you do not do that, I will just ask you what the NPC should be named.

        **Example**
           `{PREFIX}{COMMAND}`
           `{PREFIX}{COMMAND} Ecological Democratic Party`"""

        if not name:
            name = await ctx.input(
                f"{config.USER_INTERACTION_REQUIRED} Reply with the name of your new NPC."
            )

        if name.lower() == self.bot.user.name.lower():
            return await ctx.send(
                f"{config.NO} You can't have an NPC that is named after me."
            )

        if len(name) > 80:
            return await ctx.send(
                f"{config.NO} The name cannot be longer than 80 characters."
            )

        avatar_url = await self._make_avatar(ctx)

        trigger_phrase = await self._make_trigger_phrase(ctx)

        if not trigger_phrase:
            return await ctx.send(f"{config.NO} Creating NPC process was cancelled.")

        try:
            npc_record = await self.bot.db.fetchrow(
                "INSERT INTO npc (name, avatar_url, owner_id, trigger_phrase) VALUES ($1, $2, $3, $4) RETURNING *",
                name,
                avatar_url,
                ctx.author.id,
                trigger_phrase,
            )
        except asyncpg.UniqueViolationError:
            return await ctx.send(
                f"{config.NO} You already have an NPC with either that same name, "
                f"or that same trigger phrase."
            )

        example = trigger_phrase.replace("text", "Hello!")
        await ctx.send(
            f"{config.YES} The NPC #{npc_record['id']} `{name}` was created. Try speaking as them "
            f"with `{example}`. \n{config.HINT} You can allow other people to speak as this "
            f"NPC with `{config.BOT_PREFIX}npc share {npc_record['id']}`.\n{config.HINT} The "
            f"`{config.BOT_PREFIX}npc automatic` command can be used to let you automatically speak "
            f"as this NPC in certain channels, without having to use the trigger phrase.\n{config.HINT} "
            f"You can react with :wastebasket: to a message from your NPC to delete it, or with "
            f":pencil: to edit it."
        )

        self._npc_cache[npc_record["id"]] = dict(npc_record)
        self._npc_access_cache[ctx.author.id].add(npc_record["id"])

    @npc.command(name="edit", aliases=["change", "update"])
    async def edit_npc(self, ctx, *, npc: Fuzzy[NPCConverter]):
        """Edit the name, avatar and/or trigger phrase of one of your NPCs

        **Example**
           `{PREFIX}{COMMAND} 2` using the NPC's ID
           `{PREFIX}{COMMAND} Ecological Democratic Party` using the NPC's name"""

        menu = text.EditModelMenu(
            choices_with_formatted_explanation={
                "name": "Name",
                "avatar": "Avatar",
                "trigger_phrase": "Trigger Phrase",
            }
        )
        result = await menu.prompt(ctx)

        if not result.confirmed:
            return await ctx.send(f"{config.NO} You didn't decide on what to edit.")

        to_change = result.choices

        if True not in to_change.values():
            return await ctx.send(f"{config.NO} You didn't decide on what to edit.")

        if to_change["name"]:
            name = await ctx.input(
                f"{config.USER_INTERACTION_REQUIRED} Reply with the new name of your NPC."
                f"\n{config.HINT} The current name is: `{npc.name}`",
            )

            if name.lower() == self.bot.user.name.lower():
                return await ctx.send(
                    f"{config.NO} You can't have an NPC that is named after me."
                )
        else:
            name = npc.name
        if to_change["avatar"]:
            avatar_url = await self._make_avatar(ctx)
        else:
            avatar_url = npc.avatar_url

        if to_change["trigger_phrase"]:
            trigger_phrase = await self._make_trigger_phrase(
                ctx, edit=True, old_phrase=npc.trigger_phrase
            )

            if not trigger_phrase:
                await ctx.send(
                    f"{config.HINT} *Using the existing trigger phrase `{npc.trigger_phrase}`.*"
                )
                trigger_phrase = npc.trigger_phrase
        else:
            trigger_phrase = npc.trigger_phrase

        are_you_sure = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to edit your NPC `{npc.name}`?"
        )

        if not are_you_sure:
            return await ctx.send("Cancelled.")

        try:
            new_npc = await self.bot.db.fetchrow(
                "UPDATE npc SET name = $1, avatar_url = $2, trigger_phrase = $3 WHERE id = $4 RETURNING *",
                name,
                avatar_url,
                trigger_phrase,
                npc.id,
            )
        except asyncpg.UniqueViolationError:
            return await ctx.send(
                f"{config.NO} You already have a different NPC with either that same new name, "
                f"or that same new trigger phrase."
            )

        self._npc_cache[npc.id] = dict(new_npc)
        await ctx.send(f"{config.YES} Your NPC was edited.")

    @npc.command(name="delete", aliases=["remove"])
    async def remove_npc(self, ctx, *, npc: Fuzzy[NPCConverter]):
        """Delete one of your NPCs

        **Example**
           `{PREFIX}{COMMAND} 2` using the NPC's ID
           `{PREFIX}{COMMAND} Ecological Democratic Party` using the NPC's name"""

        await self.bot.db.execute(
            "DELETE FROM npc WHERE id = $1 AND owner_id = $2", npc.id, ctx.author.id
        )
        await self._load_npc_cache()
        await self._load_automatic_trigger_cache()
        await ctx.send(f"{config.YES} `{npc.name}` was deleted.")

    @npc.command(name="list", aliases=["from", "by", "f", "l"])
    async def list_npcs(
        self,
        ctx: CustomContext,
        *,
        person: Fuzzy[
            converter.CaseInsensitiveMember,
            converter.CaseInsensitiveUser,
            FuzzySettings(weights=(5, 1)),
        ] = None,
    ):
        """List every NPC you or someone else has access to

        **Example**
           `{PREFIX}{COMMAND}` list all of your NPCs
           `{PREFIX}{COMMAND} @DerJonas` to see what NPCs someone else has access to
           `{PREFIX}{COMMAND} DerJonas#8036`
           `{PREFIX}{COMMAND} Jonas`"""

        member = person or ctx.author
        npcs = [self._npc_cache[i] for i in self._npc_access_cache[member.id]]
        npcs.sort(key=lambda npc: npc["id"])

        pretty_npcs = []

        for record in npcs:
            avatar = (
                f"[Avatar]({record['avatar_url']})\n" if record["avatar_url"] else ""
            )

            owner = self.bot.get_user(record["owner_id"])
            owner_value = "\n" if not owner else f"Owner: {owner.mention} ({owner})\n"

            pretty_npcs.append(f"**__NPC #{record['id']} - {record['name']}__**")
            pretty_npcs.append(f"{avatar}Trigger Phrase: `{record['trigger_phrase']}`")
            pretty_npcs.append(owner_value)

        if pretty_npcs:
            pretty_npcs.insert(
                0,
                f"You can create a new NPC with `{config.BOT_PREFIX}npc create`, "
                f"or edit the name, avatar and/or trigger phrase of an existing one with "
                f"`{config.BOT_PREFIX}npc edit <npc>`.\n",
            )

        pages = paginator.SimplePages(
            author=f"{member.display_name}'s NPCs",
            icon=member.avatar.url,
            entries=pretty_npcs,
            per_page=20,
            empty_message="This person hasn't made any NPCs yet.",
        )
        await pages.start(ctx)

    @npc.command(name="info", aliases=["information", "show"])
    async def info(self, ctx, *, npc: Fuzzy[AnyNPCConverter]):
        """Detailed information about an existing NPC

        You do not have to have access to this NPC to use this command.

        **Example**
           `{PREFIX}{COMMAND} 2` using the NPC's ID
           `{PREFIX}{COMMAND} Ecological Democratic Party` using the NPC's name"""

        has_access = npc.id in self._npc_access_cache[ctx.author.id]
        is_owner = npc.owner_id == ctx.author.id

        embed = text.SafeEmbed()

        if is_owner:
            embed.description = (
                f"You, the owner of this NPC, can edit the name, avatar and/or the trigger "
                f"phrase of this NPC with `{config.BOT_PREFIX}npc edit {npc.id}`."
            )

        embed.set_author(
            name=f"NPC #{npc.id} - {npc.name}",
            icon_url=npc.avatar_url
            or "https://cdn.discordapp.com/avatars/487345900239323147/79c38314283392c7e21bab76f77e09e9.png",
        )

        if npc.avatar_url:
            embed.set_thumbnail(url=npc.avatar_url)

        embed.add_field(name="Owner", value=f"{npc.owner.mention} {npc.owner}")

        embed.add_field(
            name="Trigger Phrase",
            value=f"`{npc.trigger_phrase}`\n\nPeople with access to this NPC can send messages like this: "
            f"`{npc.trigger_phrase.replace('text', 'Hello!')}`",
            inline=False,
        )

        allowed_people = await self.bot.db.fetch(
            "SELECT user_id FROM npc_allowed_user WHERE npc_id = $1", npc.id
        )
        pretty_people = []

        if is_owner:
            pretty_people.append(
                f"You, the owner of this NPC, can allow other people to speak as this NPC with "
                f"`{config.BOT_PREFIX}npc share {npc.id}`, or deny someone that you previously "
                f"allowed with `{config.BOT_PREFIX}npc unshare {npc.id}`.\n"
            )

        pretty_people.append(f"{npc.owner.mention} ({npc.owner})")

        for record in allowed_people:
            user = self.bot.dciv.get_member(record["user_id"]) or self.bot.get_user(
                record["user_id"]
            )

            if user:
                pretty_people.append(f"{user.mention} ({user})")

        embed.add_field(
            name="People with access to this NPC",
            value="\n".join(pretty_people),
            inline=False,
        )

        if ctx.guild and has_access:
            automatic_channel = await self.bot.db.fetch(
                "SELECT channel_id FROM npc_automatic_mode WHERE user_id = $1 AND guild_id = $2 AND npc_id = $3",
                ctx.author.id,
                ctx.guild.id,
                npc.id,
            )

            pretty_chan = []

            for chan in automatic_channel:
                c = ctx.guild.get_channel(chan["channel_id"])
                pretty_chan.append(
                    f"{c.mention if type(c) is discord.TextChannel else f'{c.name} Category'}"
                )

            embed.add_field(
                name="Automatic Mode",
                value="\n".join(pretty_chan)
                or "__You__ don't have automatic mode enabled for this "
                "NPC in any channel or channel category on __this__ "
                "server.",
            )
        await ctx.send(embed=embed)

    @npc.group(
        name="automatic",
        aliases=["auto"],
        invoke_without_command=True,
        case_insensitive=True,
    )
    @commands.guild_only()
    async def automatic(self, ctx: CustomContext):
        """Automatically write as an NPC in a specific channel or channel category without having to use its trigger phrase"""
        automatic_channel = await self.bot.db.fetch(
            "SELECT npc_automatic_mode.npc_id, npc_automatic_mode.channel_id FROM npc_automatic_mode "
            "WHERE npc_automatic_mode.user_id = $1 "
            "AND npc_automatic_mode.guild_id = $2",
            ctx.author.id,
            ctx.guild.id,
        )

        grouped_by_npc = collections.defaultdict(list)
        pretty = [
            f"If you want to automatically speak as an NPC in a certain channel or channel category "
            f"without having to use the trigger phrase, use `{config.BOT_PREFIX}npc automatic "
            f"on <npc>`, or disable it with "
            f"`{config.BOT_PREFIX}npc automatic off <npc>`.\n\nYou can only have one "
            f"automatic NPC per channel.\n\nIf you have one NPC as automatic in an entire category, "
            f"but a different NPC in a single channel that is that same category, and you write "
            f"something in that channel, you will only speak as the NPC for that "
            f"specific channel, and not as both NPCs.\n\n"
        ]

        for record in automatic_channel:
            grouped_by_npc[record["npc_id"]].append(
                ctx.guild.get_channel(record["channel_id"])
            )

        for k, v in grouped_by_npc.items():
            npc = self._npc_cache[k]
            pretty_chan = [
                f"- {c.mention if type(c) is discord.TextChannel else f'{c.name} Category'}"
                for c in v
            ]
            pretty_chan = "\n".join(pretty_chan)
            pretty.append(f"**__{npc['name']}__**\n{pretty_chan}\n")

        if len(pretty) > 1:
            pages = paginator.SimplePages(
                entries=pretty,
                icon=ctx.guild_icon,
                per_page=15,
                author=f"{ctx.author.display_name}'s Automatic NPCs",
            )
            await pages.start(ctx)

        else:
            embed = text.SafeEmbed(description=pretty[0])
            embed.set_author(
                name=f"{ctx.author.display_name}'s Automatic NPCs",
                icon_url=ctx.guild_icon,
            )
            await ctx.send(embed=embed)

    @automatic.command(name="on", aliases=["enable"])
    @commands.guild_only()
    async def toggle_on(self, ctx: CustomContext, *, npc: Fuzzy[AccessToNPCConverter]):
        """Enable automatic mode for an NPC you have access to

        **Example**
           `{PREFIX}{COMMAND} 2` using the NPC's ID
           `{PREFIX}{COMMAND} Ecological Democratic Party` using the NPC's name"""
        await ctx.send(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the names or mentions of the channels or "
            f"categories in which you should automatically speak as your NPC `{npc.name}` even if you "
            f"don't use its trigger phrase.\n{config.HINT} To make me give multiple channels or categories "
            f"at once, separate them with a newline."
        )

        channel = await self._get_channel_input(ctx)

        if not channel:
            return await ctx.send(
                f"{config.NO} Something went wrong, you didn't specify anything."
            )

        for c_id in channel:
            await self.bot.db.execute(
                "INSERT INTO npc_automatic_mode (npc_id, user_id, channel_id, guild_id) "
                "VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING ",
                npc.id,
                ctx.author.id,
                c_id,
                ctx.guild.id,
            )

            self._automatic_npc_cache[ctx.author.id][c_id] = npc.id

        await ctx.send(
            f"{config.YES} You will now automatically speak as your NPC `{npc.name}` "
            f"in those channels or categories."
        )

    @automatic.command(name="off", aliases=["disable"])
    @commands.guild_only()
    async def toggle_off(self, ctx: CustomContext, *, npc: Fuzzy[AccessToNPCConverter]):
        """Disable automatic mode for an NPC you have access to

        **Example**
           `{PREFIX}{COMMAND} 2` using the NPC's ID
           `{PREFIX}{COMMAND} Ecological Democratic Party` using the NPC's name"""
        await ctx.send(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the names or mentions of the channels or "
            f"categories in which you should __no longer__ automatically speak as your NPC `{npc.name}`."
            f"\n{config.HINT} To make me give multiple channels or categories "
            f"at once, separate them with a newline.\n{config.HINT} If you want to disable automatic mode in every "
            f"channel on this server, consider using `{config.BOT_PREFIX}npc automatic clear {npc.id}` instead."
        )

        channel = await self._get_channel_input(ctx)

        if not channel:
            return await ctx.send(
                f"{config.NO} Something went wrong, you didn't specify anything."
            )

        for c_id in channel:
            await self.bot.db.execute(
                "DELETE FROM npc_automatic_mode WHERE npc_id = $1 AND user_id = $2 AND channel_id = $3 ",
                npc.id,
                ctx.author.id,
                c_id,
            )

            try:
                del self._automatic_npc_cache[ctx.author.id][c_id]
            except KeyError:
                continue

        await ctx.send(
            f"{config.YES} You will __no longer__ automatically speak as "
            f"your NPC `{npc.name}` in those channels or categories."
        )

    @automatic.command(name="clear", aliases=["remove", "delete"])
    @commands.guild_only()
    async def clear(self, ctx: CustomContext, *, npc: Fuzzy[AccessToNPCConverter]):
        """Disable automatic mode for an NPC you have access to in all channels on this server at once

        **Example**
           `{PREFIX}{COMMAND} 2` using the NPC's ID
           `{PREFIX}{COMMAND} Ecological Democratic Party` using the NPC's name"""

        channel = await self.bot.db.fetch(
            "DELETE FROM npc_automatic_mode WHERE npc_id = $1 AND user_id = $2 AND guild_id = $3 RETURNING channel_id",
            npc.id,
            ctx.author.id,
            ctx.guild.id,
        )

        for record in channel:
            try:
                del self._automatic_npc_cache[ctx.author.id][record["channel_id"]]
            except KeyError:
                continue

        await ctx.send(
            f"{config.YES} You will __no longer__ automatically speak as "
            f"your NPC `{npc.name}` in any channel on this server."
        )

    async def _get_channel_input(self, ctx):
        channel_text = (await ctx.input()).splitlines()

        channel = []

        conv = Fuzzy[
            converter.CaseInsensitiveTextChannel,
            converter.CaseInsensitiveCategoryChannel,
        ]

        for chan in channel_text:
            try:
                converted = await conv.convert(ctx, chan.strip())
                channel.append(converted.id)
            except commands.BadArgument:
                continue

        return channel

    async def _get_people_input(self, ctx, npc: NPCConverter):
        people_text = (await ctx.input()).splitlines()

        people = []
        conv = Fuzzy[converter.CaseInsensitiveMember]

        for peep in people_text:
            try:
                converted = await conv.convert(ctx, peep.strip())

                if not converted.bot and converted.id != npc.owner_id:
                    people.append(converted.id)

            except commands.BadArgument:
                continue

        return people

    @npc.command(name="share", aliases=["allow"])
    @commands.guild_only()
    async def allow(self, ctx, *, npc: Fuzzy[NPCConverter]):
        """Allow other people on this server to use one of your NPCs and to speak as them

        This is especially useful for NPCs representing groups and organizations, like political parties or the government.

        **Example**
           `{PREFIX}{COMMAND} 2` using the NPC's ID
           `{PREFIX}{COMMAND} Ecological Democratic Party` using the NPC's name"""

        await ctx.send(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the names or mentions of the people that should be able "
            f"to speak as your NPC `{npc.name}`.\n{config.HINT} To make me give multiple people at once access to your NPC,"
            f" separate them with a newline."
        )

        people = await self._get_people_input(ctx, npc)

        if not people:
            return await ctx.send(
                f"{config.NO} Something went wrong, you didn't specify anybody."
            )

        for p_id in people:
            await self.bot.db.execute(
                "INSERT INTO npc_allowed_user (npc_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING ",
                npc.id,
                p_id,
            )

            self._npc_access_cache[p_id].add(npc.id)

        await ctx.send(
            f"{config.YES} Those people can now speak as your NPC `{npc.name}`."
        )

    @npc.command(name="unshare", aliases=["deny"])
    @commands.guild_only()
    async def deny(self, ctx, *, npc: Fuzzy[NPCConverter]):
        """Remove access to one of your NPCs from someone that you previously have shared

        **Example**
           `{PREFIX}{COMMAND} 2` using the NPC's ID
           `{PREFIX}{COMMAND} Ecological Democratic Party` using the NPC's name"""
        await ctx.send(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the names or mentions of the people that "
            f"should __no longer__ be able to speak as your NPC `{npc.name}`.\n{config.HINT} To make me remove "
            f"the access to your NPC from multiple people at once, separate them with a newline."
        )

        people = await self._get_people_input(ctx, npc)

        if not people:
            return await ctx.send(
                f"{config.NO} Something went wrong, you didn't specify anybody."
            )

        for p_id in people:
            await self.bot.db.execute(
                "DELETE FROM npc_allowed_user WHERE npc_id = $1 AND user_id = $2",
                npc.id,
                p_id,
            )

            self._npc_access_cache[p_id].remove(npc.id)

        await ctx.send(
            f"{config.YES} Those people can __no longer__ speak as your NPC `{npc.name}`."
        )

    async def _log_npc_usage(
        self,
        npc,
        original_message: discord.Message,
        npc_message_url: str,
        npc_message_content: str,
    ):
        if not await self.bot.get_guild_setting(
            original_message.guild.id, "logging_enabled"
        ):
            return

        log_channel = await self.bot.get_logging_channel(original_message.guild)

        if not log_channel:
            return

        embed = text.SafeEmbed(title=":disguised_face:  NPC Used")
        embed.add_field(name="NPC", value=npc["name"], inline=False)
        embed.add_field(
            name="Real Author",
            value=f"{original_message.author.mention} {original_message.author} "
            f"({original_message.author.id})",
            inline=False,
        )
        embed.add_field(
            name="Context", value=f"[Jump to Message]({npc_message_url})", inline=False
        )
        embed.add_field(name="Message", value=npc_message_content)
        await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return

        try:
            author = self._recent_npc_messages[payload.channel_id][payload.message_id]
        except KeyError:
            return

        channel = self.bot.get_guild(payload.guild_id).get_channel_or_thread(payload.channel_id)

        webhook_url = await self._get_webhook(channel)

        if not webhook_url:
            return

        webhook = discord.Webhook.from_url(webhook_url, session=self.bot.session)

        if not webhook:
            return

        user = self.bot.get_user(payload.user_id)
        jump_url = f"https://discord.com/channels/{payload.guild_id}/{payload.channel_id}/{payload.message_id}"

        if not user:
            return

        if str(payload.emoji) in ("\U0001f4dd", "\U0000270f\U0000fe0f"):
            # edit

            if author != payload.user_id:
                return

            await user.send(
                f"{config.USER_INTERACTION_REQUIRED} Reply with the updated message for "
                f"this NPC message: <{jump_url}>\n{config.HINT} This will timeout after 5 minutes."
            )

            _m = await self.bot.wait_for(
                "message",
                check=lambda m: m.author.id == payload.user_id and m.guild is None,
                timeout=300,
            )

            await webhook.edit_message(
                payload.message_id,
                content=_m.clean_content,
                allowed_mentions=discord.AllowedMentions.none(),
            )

            await user.send(f"{config.YES} The NPC's message was edited: <{jump_url}>")

        elif str(payload.emoji) == "\U0001f5d1\U0000fe0f":
            # delete

            if author != payload.user_id:
                return

            await webhook.delete_message(payload.message_id)

        elif str(payload.emoji) in ("\U00002754", "\U00002753"):
            # reveal

            written_by = self.bot.get_user(author)

            if written_by:
                await user.send(
                    f"{config.HINT} This NPC message (<{jump_url}>) was written by {written_by.mention} ({written_by})."
                )

    @commands.Cog.listener(name="on_message")
    async def npc_listener(self, message: discord.Message):
        if (
            message.author.bot
            or not message.guild
            or message.author.id not in self._npc_access_cache
        ):
            return

        ctx = await self.bot.get_context(message)

        if ctx.valid:
            return

        available_npcs = [
            self._npc_cache[i] for i in self._npc_access_cache[message.author.id]
        ]

        if not available_npcs:
            return

        try:
            auto_npc_id = self._automatic_npc_cache[message.author.id][
                message.channel.id
            ]
        except KeyError:
            if message.channel.category_id:
                try:
                    auto_npc_id = self._automatic_npc_cache[message.author.id][
                        message.channel.category_id
                    ]
                except KeyError:
                    auto_npc_id = 0
            else:
                auto_npc_id = 0

        if auto_npc_id:
            npc = self._npc_cache[auto_npc_id]
            content = message.clean_content
        else:
            if not message.content:
                # we can't check this sooner because empty messages are allowed for automatic npc invocations, for
                # example when uploading an image
                return

            prefix_and_suffixes = [
                NPCPrefixSuffix(npc["id"], *npc["trigger_phrase"].split("text"))
                for npc in available_npcs
            ]

            cntn_to_check = message.clean_content.lower()
            lines = cntn_to_check.splitlines()

            if not lines:
                return

            # indexerr
            matches = [
                match
                for match in prefix_and_suffixes
                if lines[0].startswith(match.prefix)
                and lines[-1].endswith(match.suffix)
            ]

            matches.sort(key=lambda m: len(m.prefix), reverse=True)

            try:
                match = matches[0]
                npc = self._npc_cache[match.npc_id]
            except (KeyError, IndexError):
                return

            content = message.clean_content

            if match.prefix:
                content = content[len(match.prefix) :]

            if match.suffix:
                content = content[: -len(match.suffix)]

        if not await self.bot.get_guild_setting(message.guild.id, "npc_usage_allowed"):
            await message.channel.send(
                f"{config.NO} The administrators of {message.guild.name} don't allow "
                f"the usage of NPCs on their server. This can be changed by server "
                f"administrators with the `{config.BOT_PREFIX}server npcs` command.",
                delete_after=10,
            )
            return

        file = discord.utils.MISSING

        if message.attachments:
            file = await message.attachments[0].to_file(
                spoiler=message.attachments[0].is_spoiler()
            )

        webhook_url = await self._get_webhook(message.channel)

        if not webhook_url:
            return await message.channel.send(
                f"{config.NO} I don't have permissions to manage webhooks in this channel."
            )

        webhook = discord.Webhook.from_url(webhook_url, session=self.bot.session)

        try:
            await message.delete()
        except discord.Forbidden:
            await message.channel.send(
                f"{config.NO} I don't have Manage Messages permissions here to delete "
                f"your original message.",
                delete_after=5,
            )

        try:
            msg = await webhook.send(
                username=npc["name"],
                avatar_url=npc["avatar_url"],
                content=content,
                file=file,
                wait=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.NotFound, discord.Forbidden):
            await self.bot.db.execute(
                "DELETE FROM npc_webhook WHERE channel_id = $1 AND webhook_id = $2 AND "
                "webhook_token = $3",
                message.channel.id,
                webhook.id,
                webhook.token,
            )
            new_webhook_url = await self._make_new_webhook(message.channel)

            if not new_webhook_url:
                return await message.channel.send(
                    f"{config.NO} I don't have permissions to manage webhooks in this channel."
                )

            new_webhook = discord.Webhook.from_url(
                new_webhook_url, session=self.bot.session
            )

            msg = await new_webhook.send(
                username=npc["name"],
                avatar_url=npc["avatar_url"],
                content=content,
                file=file,
                wait=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )

        jump_url = (
            f"https://discord.com/channels/{message.guild.id}/{message.channel.id}/{msg.id}"
            if msg
            else ""
        )
        msg_cntnt = msg.content[:1020] if msg else "*unknown*"

        self._recent_npc_messages[message.channel.id][msg.id] = message.author.id

        self.bot.loop.create_task(
            self._log_npc_usage(npc, message, jump_url, msg_cntnt)
        )


def setup(bot):
    bot.add_cog(NPC(bot))
