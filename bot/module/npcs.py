import typing
import discord
import collections

from discord.ext import commands
from fuzzywuzzy import process
from lru import LRU

from bot.config import config
from bot.presenters import npc_forms, npcs as npc_presenter
from bot.services.npcs import NPCService
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

    def __eq__(self, other):
        return isinstance(other, NPCConverter) and other.id == self.id

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


def _split_lines(value: str) -> typing.List[str]:
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


class NPC(CustomCog):
    """NPCs can be used to write messages as someone else, for example as an role-played character, or on behalf on an organization or group."""

    def __init__(self, bot):
        super().__init__(bot)
        self.service = NPCService(bot)
        # channel_id -> webhook url
        self._webhook_cache: typing.Dict[int, str] = {}

        # npc id -> npc
        self._npc_cache: typing.Dict[int, typing.Dict] = {}

        # user_id -> set of NPC ids that user has access to
        self._npc_access_cache: typing.Dict[int, typing.Set[int]] = (
            collections.defaultdict(set)
        )

        # user id -> {channel_id -> npc_id}
        self._automatic_npc_cache: typing.Dict[int, typing.Dict[int, int]] = (
            collections.defaultdict(dict)
        )

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

        embed = npc_presenter.build_about_embed(ctx)
        await ctx.send(embed=embed)

    def _attachment_avatar_url(self, ctx: CustomContext) -> str:
        if ctx.message.attachments:
            return ctx.message.attachments[0].url
        return ""

    async def _prompt_npc_form(
        self,
        ctx: CustomContext,
        *,
        modal_factory: typing.Callable[[], npc_forms.NPCModal],
        button_label: str,
        prompt: str,
    ) -> typing.Optional[npc_forms.NPCFormResult]:
        view = text.ModalPromptView(
            ctx,
            modal_factory=modal_factory,
            button_label=button_label,
            timeout=300,
        )
        return await view.prompt_message(prompt)

    async def _send_pages(self, ctx: CustomContext, result):
        pages = paginator.SimplePages(
            entries=result.entries,
            author=result.author,
            icon=result.icon,
            empty_message=result.empty_message,
            per_page=result.per_page,
        )
        await pages.start(ctx)

    @npc.command(name="create", aliases=["make", "add"])
    async def add_npc(self, ctx: CustomContext, *, name=None):
        """Create a new NPC with a name, avatar and a trigger phrase that will be used to let you speak as that NPC

        Upload an image in the same message as this command to make me use that as your NPC's avatar.

        You can give me the name of your new NPC directly when invoking this command. If you do not do that, I will just ask you what the NPC should be named.

        **Example**
           `{PREFIX}{COMMAND}`
           `{PREFIX}{COMMAND} Ecological Democratic Party`"""

        form = await self._prompt_npc_form(
            ctx,
            modal_factory=lambda: npc_forms.NPCFormModal(
                name_default=name,
                avatar_default=self._attachment_avatar_url(ctx),
            ),
            button_label="Create NPC",
            prompt=f"{config.USER_INTERACTION_REQUIRED} Fill out the NPC details in the form.",
        )

        if form is None:
            return await ctx.send("Cancelled.")

        result = await self.service.create_npc(
            ctx,
            name=form.name,
            avatar_url=form.avatar_url,
            trigger_phrase=form.trigger_phrase,
        )
        npc_record = result.record
        await ctx.send(
            f"{result.message} \n{config.HINT} You can allow other people to speak as this "
            f"NPC with `{config.BOT_PREFIX}npc share {npc_record['id']}`.\n{config.HINT} The "
            f"`{config.BOT_PREFIX}npc automatic` command can be used to let you automatically speak "
            f"as this NPC in certain channels, without having to use the trigger phrase.\n{config.HINT} "
            f"You can react with :wastebasket: to a message from your NPC to delete it, or with "
            f":pencil: to edit it."
        )

    @npc.command(name="edit", aliases=["change", "update"])
    async def edit_npc(self, ctx, *, npc: Fuzzy[NPCConverter]):
        """Edit the name, avatar and/or trigger phrase of one of your NPCs

        **Example**
           `{PREFIX}{COMMAND} 2` using the NPC's ID
           `{PREFIX}{COMMAND} Ecological Democratic Party` using the NPC's name"""

        form = await self._prompt_npc_form(
            ctx,
            modal_factory=lambda: npc_forms.NPCFormModal(npc=npc),
            button_label="Edit NPC",
            prompt=(
                f"{config.USER_INTERACTION_REQUIRED} Update NPC #{npc.id} `{npc.name}` "
                "in the form. Leave pre-filled values unchanged to keep them."
            ),
        )

        if form is None:
            return await ctx.send("Cancelled.")

        are_you_sure = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to edit your NPC `{npc.name}`?"
        )

        if not are_you_sure:
            return await ctx.send("Cancelled.")

        result = await self.service.edit_npc(
            npc=npc,
            name=form.name,
            avatar_url=form.avatar_url,
            trigger_phrase=form.trigger_phrase,
        )
        await ctx.send(result.message)

    @npc.command(name="delete", aliases=["remove"])
    async def remove_npc(self, ctx, *, npc: Fuzzy[NPCConverter]):
        """Delete one of your NPCs

        **Example**
           `{PREFIX}{COMMAND} 2` using the NPC's ID
           `{PREFIX}{COMMAND} Ecological Democratic Party` using the NPC's name"""

        result = await self.service.delete_npc(ctx, npc=npc)
        await ctx.send(result.message)

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
           `{PREFIX}{COMMAND} DerJonas`
           `{PREFIX}{COMMAND} Jonas`"""

        member = person or ctx.author
        records = self.service.list_accessible_records(member)
        result = npc_presenter.build_npc_list_pages(ctx, member, records)
        await self._send_pages(ctx, result)

    @npc.command(name="info", aliases=["information", "show"])
    async def info(self, ctx, *, npc: Fuzzy[AnyNPCConverter]):
        """Detailed information about an existing NPC

        You do not have to have access to this NPC to use this command.

        **Example**
           `{PREFIX}{COMMAND} 2` using the NPC's ID
           `{PREFIX}{COMMAND} Ecological Democratic Party` using the NPC's name"""

        has_access = self.service.has_access(ctx.author, npc)
        is_owner = npc.owner_id == ctx.author.id
        allowed_people = await self.service.get_allowed_people(npc)
        automatic_channels = (
            await self.service.get_automatic_channels(ctx, npc) if has_access else []
        )
        embed = npc_presenter.build_info_embed(
            ctx,
            npc=npc,
            allowed_people=allowed_people,
            automatic_channels=automatic_channels,
            has_access=has_access,
            is_owner=is_owner,
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
        records = await self.service.get_automatic_overview_records(ctx)
        display = npc_presenter.build_automatic_overview(
            ctx,
            records,
            self._npc_cache,
        )

        if display.page is not None:
            return await self._send_pages(ctx, display.page)

        await ctx.send(embed=display.embed)

    @automatic.command(name="on", aliases=["enable"])
    @commands.guild_only()
    async def toggle_on(self, ctx: CustomContext, *, npc: Fuzzy[AccessToNPCConverter]):
        """Enable automatic mode for an NPC you have access to

        **Example**
           `{PREFIX}{COMMAND} 2` using the NPC's ID
           `{PREFIX}{COMMAND} Ecological Democratic Party` using the NPC's name"""
        form = await self._prompt_npc_form(
            ctx,
            modal_factory=lambda: npc_forms.NPCAutomaticChannelsModal(add=True),
            button_label="Enable Automatic Mode",
            prompt=(
                f"{config.USER_INTERACTION_REQUIRED} Choose channels or categories for "
                f"`{npc.name}` in the form."
            ),
        )

        if form is None:
            return await ctx.send("Cancelled.")

        channels = await self._get_channel_input(ctx, form.channels_text)
        result = await self.service.update_automatic(
            ctx,
            npc=npc,
            channels=channels,
            add=True,
        )
        await ctx.send(result.message)

    @automatic.command(name="off", aliases=["disable"])
    @commands.guild_only()
    async def toggle_off(self, ctx: CustomContext, *, npc: Fuzzy[AccessToNPCConverter]):
        """Disable automatic mode for an NPC you have access to

        **Example**
           `{PREFIX}{COMMAND} 2` using the NPC's ID
           `{PREFIX}{COMMAND} Ecological Democratic Party` using the NPC's name"""
        form = await self._prompt_npc_form(
            ctx,
            modal_factory=lambda: npc_forms.NPCAutomaticChannelsModal(add=False),
            button_label="Disable Automatic Mode",
            prompt=(
                f"{config.USER_INTERACTION_REQUIRED} Choose channels or categories to disable "
                f"for `{npc.name}` in the form."
            ),
        )

        if form is None:
            return await ctx.send("Cancelled.")

        channels = await self._get_channel_input(ctx, form.channels_text)
        result = await self.service.update_automatic(
            ctx,
            npc=npc,
            channels=channels,
            add=False,
        )
        await ctx.send(result.message)

    @automatic.command(name="clear", aliases=["remove", "delete"])
    @commands.guild_only()
    async def clear(self, ctx: CustomContext, *, npc: Fuzzy[AccessToNPCConverter]):
        """Disable automatic mode for an NPC you have access to in all channels on this server at once

        **Example**
           `{PREFIX}{COMMAND} 2` using the NPC's ID
           `{PREFIX}{COMMAND} Ecological Democratic Party` using the NPC's name"""

        result = await self.service.clear_automatic(ctx, npc=npc)
        await ctx.send(result.message)

    async def _get_channel_input(self, ctx, channel_text: str):
        channel = []

        conv = Fuzzy[
            converter.CaseInsensitiveTextChannel,
            converter.CaseInsensitiveCategoryChannel,
        ]

        for chan in _split_lines(channel_text):
            try:
                converted = await conv.convert(ctx, chan)
                channel.append(converted)
            except commands.BadArgument:
                continue

        return channel

    async def _get_people_input(self, ctx, npc: NPCConverter, people_text: str):
        people = []
        conv = Fuzzy[converter.CaseInsensitiveMember]

        for peep in _split_lines(people_text):
            try:
                converted = await conv.convert(ctx, peep)

                if not converted.bot and converted.id != npc.owner_id:
                    people.append(converted)

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

        form = await self._prompt_npc_form(
            ctx,
            modal_factory=lambda: npc_forms.NPCPeopleModal(add=True),
            button_label="Share NPC",
            prompt=f"{config.USER_INTERACTION_REQUIRED} Add people who can speak as `{npc.name}` in the form.",
        )

        if form is None:
            return await ctx.send("Cancelled.")

        people = await self._get_people_input(ctx, npc, form.people_text)

        result = await self.service.update_access(npc=npc, people=people, add=True)
        await ctx.send(result.message)

    @npc.command(name="unshare", aliases=["deny"])
    @commands.guild_only()
    async def deny(self, ctx, *, npc: Fuzzy[NPCConverter]):
        """Remove access to one of your NPCs from someone that you previously have shared

        **Example**
           `{PREFIX}{COMMAND} 2` using the NPC's ID
           `{PREFIX}{COMMAND} Ecological Democratic Party` using the NPC's name"""
        form = await self._prompt_npc_form(
            ctx,
            modal_factory=lambda: npc_forms.NPCPeopleModal(add=False),
            button_label="Unshare NPC",
            prompt=f"{config.USER_INTERACTION_REQUIRED} Remove people from `{npc.name}` in the form.",
        )

        if form is None:
            return await ctx.send("Cancelled.")

        people = await self._get_people_input(ctx, npc, form.people_text)
        result = await self.service.update_access(npc=npc, people=people, add=False)
        await ctx.send(result.message)

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

        channel = self.bot.get_guild(payload.guild_id).get_channel_or_thread(
            payload.channel_id
        )

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

        send_to_thread = discord.utils.MISSING

        if isinstance(message.channel, discord.Thread):
            send_to_thread = message.channel
            webhook_channel = message.channel.parent

        else:
            webhook_channel = message.channel

        webhook_url = await self._get_webhook(webhook_channel)

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
                thread=send_to_thread,
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
            new_webhook_url = await self._make_new_webhook(webhook_channel)

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
                thread=send_to_thread,
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


async def setup(bot):
    await bot.add_cog(NPC(bot))
