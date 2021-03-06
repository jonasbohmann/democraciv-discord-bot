import collections

import asyncpg
import discord
import typing

from discord.ext import commands, menus

from bot.config import config
from bot.utils.context import CustomContext, CustomCog
from bot.utils import text, converter, paginator

# TODO
# - edit proxy message  (dms by reaction, else ctx)
# - remove proxy message
# - reveal proxy message (dms by reaction, else ctx)
# - npc model
# - cache or db
# - EditXMenu superclass

NPCPrefixSuffix = collections.namedtuple("NPCPrefixSuffix", ["npc_id", "prefix", "suffix"])


class OwnNPCConverter(commands.Converter):
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

        match = await ctx.bot.db.fetchrow("SELECT * FROM npc WHERE (lower(name) = $1 OR id = $2) AND owner_id = $3",
                                          arg, arg_id, ctx.author.id)

        if match:
            return dict(match)

        raise commands.BadArgument(f"{config.NO} You don't have an NPC that matches `{argument}`.")


class AccessToNPCConverter(OwnNPCConverter):
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
                return dict(match)

            raise commands.BadArgument(f"{config.NO} You don't have access to an NPC that matches `{argument}`.")


class EditNPCMenu(menus.Menu):
    def __init__(self):
        super().__init__(timeout=120.0, delete_message_after=True)
        self._make_result()

    def _make_result(self):
        self.result = collections.namedtuple("EditNPCMenuResult", ["confirmed", "result"])
        self.result.confirmed = False
        self.result.result = {"name": False, "avatar": False, "trigger_phrase": False}
        return self.result

    async def send_initial_message(self, ctx, channel):
        embed = text.SafeEmbed(
            title=f"{config.USER_INTERACTION_REQUIRED}  What do you want to edit?",
            description=f"Select as many things as you want, then click "
                        f"the {config.YES} button to continue, or {config.NO} to cancel.\n\n"
                        f":one: Name\n"
                        f":two: Avatar\n"
                        f":three: Trigger Phrase",
        )
        return await ctx.send(embed=embed)

    @menus.button("1\N{variation selector-16}\N{combining enclosing keycap}")
    async def on_first_choice(self, payload):
        self.result.result["name"] = not self.result.result["name"]

    @menus.button("2\N{variation selector-16}\N{combining enclosing keycap}")
    async def on_second_choice(self, payload):
        self.result.result["avatar"] = not self.result.result["avatar"]

    @menus.button("3\N{variation selector-16}\N{combining enclosing keycap}")
    async def on_third_choice(self, payload):
        self.result.result["trigger_phrase"] = not self.result.result["trigger_phrase"]

    @menus.button(config.YES)
    async def confirm(self, payload):
        self.result.confirmed = True
        self.stop()

    @menus.button(config.NO)
    async def cancel(self, payload):
        self._make_result()
        self.stop()

    async def prompt(self, ctx):
        await self.start(ctx, wait=True)
        return self.result


class NPC(CustomCog):
    """NPCs can be used to write messages as someone else, for example as an role-played character, or on behalf on an organization or group."""

    def __init__(self, bot):
        super().__init__(bot)
        # channel_id -> webhook object
        self._webhook_cache: typing.Dict[int, str] = {}

        # npc id -> npc
        self._npc_cache: typing.Dict[int, typing.Dict] = {}

        # owner_id -> list of NPC ids that owner has access to
        self._npc_access_cache: typing.Dict[int, typing.List[int]] = collections.defaultdict(list)

        # user id -> {channel_id -> npc_id}
        self._automatic_npc_cache: typing.Dict[int, typing.Dict[int, int]] = collections.defaultdict(dict)

        self.bot.loop.create_task(self._make_webhook_adapter())
        self.bot.loop.create_task(self._load_webhook_cache())
        self.bot.loop.create_task(self._load_npc_cache())
        self.bot.loop.create_task(self._load_automatic_trigger_cache())

    async def _make_webhook_adapter(self):
        await self.bot.wait_until_ready()
        self._adapter = discord.AsyncWebhookAdapter(session=self.bot.session)

    async def _load_webhook_cache(self):
        await self.bot.wait_until_ready()

        webhooks = await self.bot.db.fetch("SELECT channel_id, webhook_id, webhook_token FROM npc_webhook")
        # adapter = discord.AsyncWebhookAdapter(session=self.bot.session)

        for record in webhooks:
            webhook_url = f"https://discord.com/api/webhooks/{record['webhook_id']}/{record['webhook_token']}"
            # webhook = discord.Webhook.partial(id=record['webhook_id'], token=record['webhook_token'], adapter=adapter)
            self._webhook_cache[record['channel_id']] = webhook_url

    async def _load_npc_cache(self):
        await self.bot.wait_until_ready()

        npcs = await self.bot.db.fetch(
            "SELECT npc.id, npc.name, npc.avatar_url, npc.owner_id, npc.trigger_phrase FROM npc")

        for record in npcs:
            self._npc_cache[record['id']] = dict(record)
            self._npc_access_cache[record['owner_id']].append(record['id'])

            others = await self.bot.db.fetch("SELECT user_id FROM npc_allowed_user WHERE npc_id = $1", record['id'])

            for other in others:
                self._npc_access_cache[other['user_id']].append(record['id'])

    async def _load_automatic_trigger_cache(self):
        await self.bot.wait_until_ready()

        npcs = await self.bot.db.fetch("SELECT * FROM npc_automatic_mode")

        for record in npcs:
            self._automatic_npc_cache[record['user_id']][record['channel_id']] = record['npc_id']

    async def _make_new_webhook(self, channel: discord.TextChannel):
        try:
            webhook: discord.Webhook = await channel.create_webhook(name="NPC Hook",
                                                                    avatar=await self.bot.avatar_bytes())

            await self.bot.db.execute("INSERT INTO npc_webhook (guild_id, channel_id, webhook_id, "
                                      "webhook_token) VALUES ($1, $2, $3, $4)", channel.guild.id, channel.id,
                                      webhook.id, webhook.token)

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

    @commands.group(name="npc", invoke_without_command=True, case_insensitive=True)
    async def npc(self, ctx: CustomContext):
        """What is an NPC?"""
        embed = text.SafeEmbed(title="NPCs", description="This is still in development.")
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
                f"want your NPC to have an avatar (yet), just reply with gibberish.",
                image_allowed=True)

            if avatar.lower().startswith("http") and avatar.lower().endswith(("png", "jpeg", "jpg", "gif", "webp")):
                avatar_url = avatar

        return avatar_url

    async def _make_trigger_phrase(self, ctx, *, edit=False, old_phrase=""):
        bot_prefixes = ", ".join([f"`{pref}`" for pref in config.BOT_ADDITIONAL_PREFIXES])

        msg = (f"{config.USER_INTERACTION_REQUIRED} How would you like to trigger your NPC? "
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
            await ctx.send(f"{config.NO} You have to surround the word `text` with a prefix and/or a suffix."
                           f"\n{config.HINT} For example, making the trigger phrase `<<text>>` would "
                           f"mean you had to write `<<Hello!>>` to make your NPC say `Hello!`.")
            return

        if trigger_phrase.startswith(tuple(config.BOT_ADDITIONAL_PREFIXES)):
            await ctx.send(f"{config.NO} Your trigger phrase can't have any of "
                           f"my bot prefixes at the beginning.")
            return

        if "text" not in trigger_phrase:
            await ctx.send(f"{config.NO} You have to reply with the word `text` surrounded with a prefix and/or "
                           f"a suffix. For example, making the trigger phrase `<<text` would mean "
                           f"you had to write `<<Hello!` to make your NPC say `Hello!`.")
            return

        prefix, suffix = trigger_phrase.split("text")

        if not prefix and not suffix:
            await ctx.send(f"{config.NO} You have to surround the word `text` with a prefix and/or a suffix. "
                           f"For example, making the trigger phrase `<<text` would "
                           f"mean you had to write `<<Hello!` to make your NPC say `Hello!`.")
            return

        return trigger_phrase

    @npc.command(name="create", aliases=['make', 'add'])
    async def add_npc(self, ctx: CustomContext, *, name=None):
        """Create a new NPC with a name, avatar and a trigger phrase that will be used to let you speak as that NPC

        Upload an image in the same message as this command to make me use that as your NPC's avatar.

        You can give me the name of your new NPC directly when invoking this command. If you do not do that, I will just ask you what the NPC should be named.

        **Example**
           `{PREFIX}{COMMAND}`
           `{PREFIX}{COMMAND} Ecological Democratic Party`"""

        if not name:
            name = await ctx.input(f"{config.USER_INTERACTION_REQUIRED} Reply with the name of your new NPC.")

        if name.lower() == self.bot.user.name.lower():
            return await ctx.send(f"{config.NO} You can't have an NPC that is named after me.")

        avatar_url = await self._make_avatar(ctx)
        trigger_phrase = await self._make_trigger_phrase(ctx)

        try:
            npc_record = await self.bot.db.fetchrow(
                "INSERT INTO npc (name, avatar_url, owner_id, trigger_phrase) VALUES ($1, $2, $3, $4) RETURNING *",
                name, avatar_url, ctx.author.id, trigger_phrase)
        except asyncpg.UniqueViolationError:
            return await ctx.send(f"{config.NO} You already have an NPC with either that same name, "
                                  f"or that same trigger phrase.")

        self._npc_cache[npc_record['id']] = dict(npc_record)
        self._npc_access_cache[ctx.author.id].append(npc_record['id'])

        example = trigger_phrase.replace("text", "Hello!")
        await ctx.send(f"{config.YES} Your NPC `{name}` was created. Try speaking as them with `{example}`.")

    @npc.command(name="edit", aliases=['change', 'update'])
    async def edit_npc(self, ctx, *, npc: OwnNPCConverter):
        """Edit the name, avatar and/or trigger phrase of one of your NPCs

        **Example**
           `{PREFIX}{COMMAND} 2` using the NPC's ID
           `{PREFIX}{COMMAND} Ecological Democratic Party` using the NPC's name"""

        result = await EditNPCMenu().prompt(ctx)

        if not result.confirmed:
            return await ctx.send(f"{config.NO} You didn't decide on what to edit.")

        to_change = result.result

        if True not in to_change.values():
            return await ctx.send(f"{config.NO} You didn't decide on what to edit.")

        if to_change["name"]:
            name = await ctx.input(
                f"{config.USER_INTERACTION_REQUIRED} Reply with the new name of your NPC."
                f"\n{config.HINT} The current name is `{npc['name']}`",
            )

            if name.lower() == self.bot.user.name.lower():
                return await ctx.send(f"{config.NO} You can't have an NPC that is named after me.")
        else:
            name = npc['name']

        if to_change["avatar"]:
            avatar_url = await self._make_avatar(ctx)
        else:
            avatar_url = npc['avatar_url']

        if to_change["trigger_phrase"]:
            trigger_phrase = await self._make_trigger_phrase(ctx, edit=True, old_phrase=npc['trigger_phrase'])
        else:
            trigger_phrase = npc['trigger_phrase']

        are_you_sure = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to edit your NPC `{npc['name']}`?"
        )

        if not are_you_sure:
            return await ctx.send("Cancelled.")

        try:
            new_npc = await self.bot.db.fetchrow(
                "UPDATE npc SET name = $1, avatar_url = $2, trigger_phrase = $3 WHERE id = $4 RETURNING *",
                name,
                avatar_url,
                trigger_phrase,
                npc['id']
            )
        except asyncpg.UniqueViolationError:
            return await ctx.send(f"{config.NO} You already have a different NPC with either that same new name, "
                                  f"or that same new trigger phrase.")

        self._npc_cache[npc['id']] = dict(new_npc)
        await ctx.send(f"{config.YES} Your NPC was edited.")

    @npc.command(name="delete", aliases=['remove'])
    async def remove_npc(self, ctx, *, npc: OwnNPCConverter):
        """Delete one of your NPCs

        **Example**
           `{PREFIX}{COMMAND} 2` using the NPC's ID
           `{PREFIX}{COMMAND} Ecological Democratic Party` using the NPC's name"""

        await self.bot.db.execute("DELETE FROM npc WHERE name = $1 AND owner_id = $2", npc['name'], ctx.author.id)
        self._npc_cache.pop(npc['id'])
        await ctx.send(f"{config.YES} `{npc['name']}` was deleted.")

    @npc.command(name="list")
    async def list_npcs(self, ctx: CustomContext, *, member: typing.Union[
        converter.CaseInsensitiveMember, converter.CaseInsensitiveUser, converter.FuzzyCIMember] = None):
        """List every NPC you or someone else has access to

        **Example**
           `{PREFIX}{COMMAND}` list all of your NPCs
           `{PREFIX}{COMMAND} @DerJonas` see to what NPCs someone else has access to
           `{PREFIX}{COMMAND} DerJonas#8036`
           `{PREFIX}{COMMAND} Jonas`"""

        member = member or ctx.author

        sql = """SELECT npc.id, npc.name, npc.avatar_url, npc.owner_id, npc.trigger_phrase FROM npc 
        FULL JOIN npc_allowed_user allowed ON allowed.npc_id = npc.id WHERE (npc.owner_id = $1 OR allowed.user_id = $1) ORDER BY npc.id"""

        npcs = await self.bot.db.fetch(sql, member.id)

        pretty_npcs = []

        for record in npcs:
            avatar = f"[Avatar]({record['avatar_url']})\n" if record['avatar_url'] else ""
            pretty_npcs.append(
                f"**__#{record['id']} - {record['name']}__**\n{avatar}Trigger Phrase: `{record['trigger_phrase']}`\n")

        if pretty_npcs:
            pretty_npcs.insert(0, f"You can add a new NPC with `{config.BOT_PREFIX}npc add`, "
                                  f"or edit an existing one with `{config.BOT_PREFIX}npc edit <npc name>`.\n")

        pages = paginator.SimplePages(author=f"{member.display_name}'s NPCs",
                                      icon=member.avatar_url_as(static_format="png"),
                                      entries=pretty_npcs,
                                      empty_message="This person hasn't made any NPCs yet.")
        await pages.start(ctx)

    @npc.command(name="info", aliases=['information', 'show'])
    async def info(self, ctx, *, npc: OwnNPCConverter):
        """Detailed information about one of your NPCs

        **Example**
           `{PREFIX}{COMMAND} 2` using the NPC's ID
           `{PREFIX}{COMMAND} Ecological Democratic Party` using the NPC's name"""

        embed = text.SafeEmbed(description=f"You can edit this NPC with `{config.BOT_PREFIX}npc edit {npc['id']}`, "
                                           f"or delete it with `{config.BOT_PREFIX}npc delete {npc['id']}`.")

        embed.set_author(name=f"NPC #{npc['id']} - {npc['name']}",
                         icon_url=npc['avatar_url'] or self.bot.user.avatar_url_as(static_format="png"))

        if npc['avatar_url']:
            embed.set_thumbnail(url=npc['avatar_url'])

        embed.add_field(name="Trigger Phrase",
                        value=f"`{npc['trigger_phrase']}`\n\nSend messages as this NPC like this: "
                              f"`{npc['trigger_phrase'].replace('text', 'Hello!')}`",
                        inline=False)

        allowed_people = await self.bot.db.fetch("SELECT user_id FROM npc_allowed_user WHERE npc_id = $1", npc['id'])
        pretty_people = [f"Allow other people to speak as this NPC with `{config.BOT_PREFIX}npc allow {npc['id']}`, "
                         f"or deny someone you previously allowed with `{config.BOT_PREFIX}npc deny {npc['id']}`.\n",
                         f"{ctx.author.mention} ({ctx.author})"]

        for record in allowed_people:
            user = self.bot.dciv.get_member(record['user_id']) or self.bot.get_user(record['user_id'])

            if user:
                pretty_people.append(f"{user.mention} ({user})")

        embed.add_field(name="People with access to this NPC",
                        value="\n".join(pretty_people),
                        inline=False)
        await ctx.send(embed=embed)

    @npc.group(name="automatic", aliases=['auto'], invoke_without_command=True, case_insensitive=True)
    @commands.guild_only()
    async def automatic(self, ctx: CustomContext):
        """Automatically write as an NPC in a specific channel or channel category without having to use its trigger phrase"""
        automatic_channel = await self.bot.db.fetch(
            "SELECT npc_automatic_mode.npc_id, npc_automatic_mode.channel_id FROM npc_automatic_mode "
            "WHERE npc_automatic_mode.user_id = $1 "
            "AND npc_automatic_mode.guild_id = $2",
            ctx.author.id, ctx.guild.id)

        grouped_by_npc = collections.defaultdict(list)
        pretty = []

        for record in automatic_channel:
            grouped_by_npc[record['npc_id']].append(ctx.guild.get_channel(record['channel_id']))

        for k, v in grouped_by_npc.items():
            npc = self._npc_cache[k]
            pretty_chan = [f"- {c.mention if type(c) is discord.TextChannel else f'{c.name} Category'}" for c in v]
            pretty_chan = "\n".join(pretty_chan)
            pretty.append(f"**__{npc['name']}__**\n{pretty_chan}\n")

        if pretty:
            pretty.insert(0, f"If you want to automatically speak as an NPC in a certain channel or channel category "
                             f"without having to use the trigger phrase, use `{config.BOT_PREFIX}npc automatic "
                             f"on <npc name>`, or disable it with "
                             f"`{config.BOT_PREFIX}npc automatic off <npc name>`.\n\nYou can only have one "
                             f"automatic NPC per channel.\n\nIf you have one NPC as automatic in an entire category, "
                             f"but a different NPC in a single channel that is that same category, and you write "
                             f"something in that channel, you will only speak as the NPC for that "
                             f"specific channel, and not as both NPCs.\n\n")

        pages = paginator.SimplePages(entries=pretty,
                                      icon=ctx.guild_icon,
                                      author=f"{ctx.author.display_name}'s Automatic NPCs",
                                      empty_message="You don't have any automatic NPCs in "
                                                    "any channel or category on this server.")
        await pages.start(ctx)

    @automatic.command(name="on", aliases=['enable'])
    @commands.guild_only()
    async def toggle_on(self, ctx: CustomContext, *, npc: AccessToNPCConverter):
        """Enable automatic mode for an NPC you have access to

        **Example**
           `{PREFIX}{COMMAND} 2` using the NPC's ID
           `{PREFIX}{COMMAND} Ecological Democratic Party` using the NPC's name"""
        await ctx.send(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the names or mentions of the channels or "
            f"categories in which you should automatically speak as your NPC `{npc['name']}` even if you "
            f"don't use its trigger phrase.\n{config.HINT} To make me give multiple channels or categories "
            f"at once, separate them with a newline."
        )

        channel = await self._get_channel_input(ctx)

        if not channel:
            return await ctx.send(f"{config.NO} Something went wrong, you didn't specify anything.")

        for c_id in channel:
            await self.bot.db.execute(
                "INSERT INTO npc_automatic_mode (npc_id, user_id, channel_id, guild_id) VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING ",
                npc['id'], ctx.author.id, c_id, ctx.guild.id
            )

            self._automatic_npc_cache[ctx.author.id][c_id] = npc['id']

        await ctx.send(f"{config.YES} You will now automatically speak as your NPC `{npc['name']}` "
                       f"in those channels or categories.")

    @automatic.command(name="off", aliases=['disable'])
    @commands.guild_only()
    async def toggle_off(self, ctx: CustomContext, *, npc: AccessToNPCConverter):
        """Disable automatic mode for an NPC you have access to

        **Example**
           `{PREFIX}{COMMAND} 2` using the NPC's ID
           `{PREFIX}{COMMAND} Ecological Democratic Party` using the NPC's name"""
        await ctx.send(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the names or mentions of the channels or "
            f"categories in which you should __no longer__ automatically speak as your NPC `{npc['name']}`."
            f"\n{config.HINT} To make me give multiple channels or categories "
            f"at once, separate them with a newline."
        )

        channel = await self._get_channel_input(ctx)

        if not channel:
            return await ctx.send(f"{config.NO} Something went wrong, you didn't specify anything.")

        for c_id in channel:
            await self.bot.db.execute(
                "DELETE FROM npc_automatic_mode WHERE npc_id = $1 AND user_id = $2 AND channel_id = $3 ",
                npc['id'], ctx.author.id, c_id
            )

            try:
                del self._automatic_npc_cache[ctx.author.id][c_id]
            except KeyError:
                continue

        await ctx.send(f"{config.YES} You will __no longer__ automatically speak as "
                       f"your NPC `{npc['name']}` in those channels or categories.")

    async def _get_channel_input(self, ctx):
        channel_text = (await ctx.input()).splitlines()

        channel = []

        for chan in channel_text:
            try:
                converted = await converter.CaseInsensitiveTextChannelOrCategoryChannel().convert(ctx, chan.strip())
                channel.append(converted.id)
            except commands.BadArgument:
                continue

        return channel

    async def _get_people_input(self, ctx, npc):
        people_text = (await ctx.input()).splitlines()

        people = []

        for peep in people_text:
            try:
                converted = await converter.CaseInsensitiveMember().convert(ctx, peep.strip())

                if not converted.bot and not converted.id == npc['owner_id']:
                    people.append(converted.id)

            except commands.BadArgument:
                try:
                    converted = await converter.FuzzyCIMember().convert(ctx, peep.strip())

                    if not converted.bot and not converted.id == npc['owner_id']:
                        people.append(converted.id)
                except commands.BadArgument:
                    continue

        return people

    @npc.command(name="allow")
    @commands.guild_only()
    async def allow(self, ctx, *, npc: OwnNPCConverter):
        """Allow other people on this server to also use one of your NPCs and to speak as them

        This is especially useful for NPCs representing groups and organizations, like political parties or the government.

        **Example**
           `{PREFIX}{COMMAND} 2` using the NPC's ID
           `{PREFIX}{COMMAND} Ecological Democratic Party` using the NPC's name"""

        await ctx.send(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the names or mentions of the people that should be able "
            f"to speak as your NPC `{npc['name']}`.\n{config.HINT} To make me give multiple people at once access to your NPC,"
            f" separate them with a newline, like in the "
            f"image below."
        )

        people = await self._get_people_input(ctx, npc)

        if not people:
            return await ctx.send(f"{config.NO} Something went wrong, you didn't specify anybody.")

        for p_id in people:
            await self.bot.db.execute(
                "INSERT INTO npc_allowed_user (npc_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING ",
                npc['id'], p_id,
            )

            self._npc_access_cache[p_id].append(npc['id'])

        await ctx.send(f"{config.YES} Those people can now speak as your NPC `{npc['name']}`.")

    @npc.command(name="deny")
    @commands.guild_only()
    async def deny(self, ctx, *, npc: OwnNPCConverter):
        """Remove access to one of your NPCs from someone that you previously have shared

        **Example**
           `{PREFIX}{COMMAND} 2` using the NPC's ID
           `{PREFIX}{COMMAND} Ecological Democratic Party` using the NPC's name"""
        await ctx.send(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the names or mentions of the people that "
            f"should __no longer__ be able to speak as your NPC `{npc['name']}`.\n{config.HINT} To make me remove "
            f"the access to your NPC from multiple people at once, separate them with a newline, like in the "
            f"image below."
        )

        people = await self._get_people_input(ctx, npc)

        if not people:
            return await ctx.send(f"{config.NO} Something went wrong, you didn't specify anybody.")

        for p_id in people:
            await self.bot.db.execute(
                "DELETE FROM npc_allowed_user WHERE npc_id = $1 AND user_id = $2",
                npc['id'], p_id,
            )

            self._npc_access_cache[p_id].remove(npc['id'])

        await ctx.send(f"{config.YES} Those people can now __no longer__ speak as your NPC `{npc['name']}`.")

    async def _log_npc_usage(self, npc, original_message: discord.Message, npc_message_url: str):
        if not await self.bot.get_guild_setting(original_message.guild.id, "logging_enabled"):
            return

        log_channel = await self.bot.get_logging_channel(original_message.guild)

        if not log_channel:
            return

        embed = text.SafeEmbed(title=":disguised_face:  NPC Used")
        embed.add_field(name="NPC", value=npc['name'], inline=False)
        embed.add_field(name="Real Author", value=f"{original_message.author} ({original_message.author.id})",
                        inline=False)
        embed.add_field(name="Message", value=f"[Jump]({npc_message_url})", inline=False)
        await log_channel.send(embed=embed)

    @commands.Cog.listener(name="on_message")
    async def npc_listener(self, message: discord.Message):
        if message.author.bot or not message.guild or message.author.id not in self._npc_access_cache:
            return

        ctx = await self.bot.get_context(message)

        if ctx.valid:
            return

        available_npcs = [self._npc_cache[i] for i in self._npc_access_cache[message.author.id]]

        if not available_npcs:
            return

        try:
            auto_npc_id = self._automatic_npc_cache[message.author.id][message.channel.id]
        except KeyError:
            if message.channel.category_id:
                try:
                    auto_npc_id = self._automatic_npc_cache[message.author.id][message.channel.category_id]
                except KeyError:
                    auto_npc_id = 0
            else:
                auto_npc_id = 0

        if auto_npc_id:
            npc = self._npc_cache[auto_npc_id]
            content = message.clean_content
        else:
            prefix_and_suffixes = [NPCPrefixSuffix(npc['id'], *npc['trigger_phrase'].split("text")) for npc in
                                   available_npcs]

            cntn_to_check = message.clean_content.lower()
            lines = cntn_to_check.splitlines()

            matches = [match for match in prefix_and_suffixes if lines[0].startswith(match.prefix)
                       and lines[-1].endswith(match.suffix)]

            matches.sort(key=lambda m: len(m.prefix), reverse=True)

            try:
                match = matches[0]
                npc = self._npc_cache[match.npc_id]
            except (KeyError, IndexError):
                return

            content = message.clean_content

            if match.prefix:
                content = content[len(match.prefix):]

            if match.suffix:
                content = content[:-len(match.suffix)]

        file = None

        if message.attachments:
            file = await message.attachments[0].to_file(spoiler=message.attachments[0].is_spoiler())

        webhook_url = await self._get_webhook(message.channel)

        if not webhook_url:
            return await message.channel.send(
                f"{config.NO} I don't have permissions to manage webhooks in this channel.")

        webhook = discord.Webhook.from_url(webhook_url, adapter=self._adapter)

        try:
            await message.delete()
        except discord.Forbidden:
            await message.channel.send(f"{config.NO} I don't have Manage Messages permissions here to delete "
                                       f"your original message.")

        try:
            msg = await webhook.send(username=npc['name'], avatar_url=npc['avatar_url'],
                                     content=content, file=file, wait=True)
        except (discord.NotFound, discord.Forbidden):
            await self.bot.db.execute("DELETE FROM npc_webhook WHERE channel_id = $1 AND webhook_id = $2 AND "
                                      "webhook_token = $3",
                                      message.channel.id, webhook.id, webhook.token)
            new_webhook_url = await self._make_new_webhook(message.channel)

            if not new_webhook_url:
                return await message.channel.send(
                    f"{config.NO} I don't have permissions to manage webhooks in this channel.")

            new_webhook = discord.Webhook.from_url(new_webhook_url, adapter=self._adapter)

            msg = await new_webhook.send(username=npc['name'], avatar_url=npc['avatar_url'],
                                         content=content, file=file, wait=True)

        jump_url = f'https://discord.com/channels/{message.guild.id}/{message.channel.id}/{msg.id}' if msg else ""
        self.bot.loop.create_task(self._log_npc_usage(npc, message, jump_url))


def setup(bot):
    bot.add_cog(NPC(bot))
