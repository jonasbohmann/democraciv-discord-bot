import collections
import typing

import asyncpg
import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import escape_markdown

from bot.config import config
from bot.module.npcs import AccessToNPCConverter, AnyNPCConverter, NPCConverter
from bot.slash import context as slash_context
from bot.slash import forms, transformers, ui
from bot.utils import exceptions, paginator, text

OwnedNPCOption = app_commands.Transform[NPCConverter, transformers.NPCTransformer]
AnyNPCOption = app_commands.Transform[AnyNPCConverter, transformers.AnyNPCTransformer]
AccessNPCOption = app_commands.Transform[
    AccessToNPCConverter,
    transformers.AccessToNPCTransformer,
]
ChannelOption = typing.Union[discord.TextChannel, discord.CategoryChannel]


class NPCFormModal(forms.ErrorHandledModal):
    def __init__(
        self,
        cog: "NPCSlash",
        *,
        npc: NPCConverter = None,
    ):
        super().__init__(title="Edit NPC" if npc else "Create NPC")
        self.cog = cog
        self.npc = npc
        self.name = forms.text_label(
            label="Name",
            default=npc.name if npc else None,
            max_length=80,
        )
        self.avatar_url = forms.text_label(
            label="Avatar URL",
            description="Optional permanent image URL.",
            default=npc.avatar_url if npc and npc.avatar_url else "",
            required=False,
            max_length=512,
        )
        self.trigger_phrase = forms.text_label(
            label="Trigger Phrase",
            description="Use `text` where the message content should go, e.g. <<text",
            default=npc.trigger_phrase if npc else None,
            max_length=100,
        )
        self.add_item(self.name)
        self.add_item(self.avatar_url)
        self.add_item(self.trigger_phrase)

    async def on_submit(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="npc edit" if self.npc else "npc create",
        )
        await ctx.defer()

        if self.npc:
            await self.cog.edit_npc(
                ctx,
                npc=self.npc,
                name=self.name.component.value,
                avatar_url=self.avatar_url.component.value,
                trigger_phrase=self.trigger_phrase.component.value,
            )
        else:
            await self.cog.create_npc(
                ctx,
                name=self.name.component.value,
                avatar_url=self.avatar_url.component.value,
                trigger_phrase=self.trigger_phrase.component.value,
            )


class NPCPeopleModal(forms.ErrorHandledModal):
    def __init__(
        self,
        cog: "NPCSlash",
        *,
        npc: NPCConverter,
        add: bool,
    ):
        super().__init__(title=f"{'Share' if add else 'Unshare'} NPC")
        self.cog = cog
        self.npc = npc
        self.add = add
        self.people = forms.text_label(
            label="People",
            description="Mentions, IDs, names, or nicknames. One per line.",
            style=discord.TextStyle.long,
        )
        self.add_item(self.people)

    async def on_submit(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="npc share-bulk" if self.add else "npc unshare-bulk",
        )
        await ctx.defer()
        people = await forms.resolve_members(
            ctx,
            self.people.component.value,
            exclude_ids={self.npc.owner_id},
        )
        await self.cog.update_access(ctx, npc=self.npc, people=people, add=self.add)


class NPCAutomaticChannelsModal(forms.ErrorHandledModal):
    def __init__(
        self,
        cog: "NPCSlash",
        *,
        npc: AccessToNPCConverter,
        add: bool,
    ):
        super().__init__(title=f"{'Enable' if add else 'Disable'} Automatic NPC")
        self.cog = cog
        self.npc = npc
        self.add = add
        self.channels = forms.text_label(
            label="Channels or Categories",
            description="Mentions, IDs, or names. One per line.",
            style=discord.TextStyle.long,
        )
        self.add_item(self.channels)

    async def on_submit(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction,
            command_name=(
                "npc automatic bulk-enable"
                if self.add
                else "npc automatic bulk-disable"
            ),
        )
        await ctx.defer()
        channels = await forms.resolve_channels(ctx, self.channels.component.value)
        await self.cog.update_automatic(
            ctx,
            npc=self.npc,
            channels=channels,
            add=self.add,
        )


class NPCSlash(commands.Cog):
    npc = app_commands.Group(
        name="npc",
        description="Create and manage roleplay NPCs.",
    )
    npc_automatic = app_commands.Group(
        name="automatic",
        description="Manage automatic NPC mode.",
        parent=npc,
    )

    def __init__(self, bot):
        self.bot = bot

    @property
    def legacy_cog(self):
        return self.bot.get_cog("NPC")

    def validate_name(self, name: str):
        name = (name or "").strip()
        if not name:
            raise exceptions.InvalidUserInputError(
                f"{config.NO} The name cannot be empty."
            )

        if name.lower() == self.bot.user.name.lower():
            raise exceptions.InvalidUserInputError(
                f"{config.NO} You can't have an NPC that is named after me."
            )

        if len(name) > 80:
            raise exceptions.InvalidUserInputError(
                f"{config.NO} The name cannot be longer than 80 characters."
            )

        return name

    def validate_trigger_phrase(self, trigger_phrase: str):
        trigger_phrase = (trigger_phrase or "").strip().lower()
        bot_prefixes = tuple(config.BOT_ADDITIONAL_PREFIXES)

        if trigger_phrase == "text":
            raise exceptions.InvalidUserInputError(
                f"{config.NO} You have to surround the word `text` with a prefix and/or suffix."
            )

        if trigger_phrase.startswith(bot_prefixes):
            raise exceptions.InvalidUserInputError(
                f"{config.NO} Your trigger phrase can't have any of my bot prefixes at the beginning."
            )

        if "text" not in trigger_phrase:
            raise exceptions.InvalidUserInputError(
                f"{config.NO} You have to include the word `text` in your trigger phrase."
            )

        prefix, suffix = trigger_phrase.split("text", maxsplit=1)
        if not prefix and not suffix:
            raise exceptions.InvalidUserInputError(
                f"{config.NO} You have to surround the word `text` with a prefix and/or suffix."
            )

        return trigger_phrase

    async def create_npc(
        self,
        ctx: slash_context.InteractionContext,
        *,
        name: str,
        avatar_url: str,
        trigger_phrase: str,
    ):
        name = self.validate_name(name)
        avatar_url = (avatar_url or "").strip() or None
        trigger_phrase = self.validate_trigger_phrase(trigger_phrase)

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
                f"{config.NO} You already have an NPC with either that same name, or that same trigger phrase.",
                ephemeral=True,
            )

        self.legacy_cog._npc_cache[npc_record["id"]] = dict(npc_record)
        self.legacy_cog._npc_access_cache[ctx.author.id].add(npc_record["id"])

        example = trigger_phrase.replace("text", "Hello!")
        await ctx.send(
            f"{config.YES} The NPC #{npc_record['id']} `{name}` was created. Try speaking as them with `{example}`.",
        )

    async def edit_npc(
        self,
        ctx: slash_context.InteractionContext,
        *,
        npc: NPCConverter,
        name: str,
        avatar_url: str,
        trigger_phrase: str,
    ):
        name = self.validate_name(name)
        avatar_url = (avatar_url or "").strip() or None
        trigger_phrase = self.validate_trigger_phrase(trigger_phrase)

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
                f"{config.NO} You already have a different NPC with either that same new name, or that same new trigger phrase.",
                ephemeral=True,
            )

        self.legacy_cog._npc_cache[npc.id] = dict(new_npc)
        await ctx.send(f"{config.YES} Your NPC was edited.")

    async def update_access(
        self,
        ctx: slash_context.InteractionContext,
        *,
        npc: NPCConverter,
        people,
        add: bool,
    ):
        if not people:
            return await ctx.send(
                f"{config.NO} Something went wrong, you didn't specify anybody.",
                ephemeral=True,
            )

        people = [
            person
            for person in people
            if not getattr(person, "bot", False) and person.id != npc.owner_id
        ]
        if not people:
            return await ctx.send(
                f"{config.NO} No valid people were specified.",
                ephemeral=True,
            )

        for person in people:
            if add:
                await self.bot.db.execute(
                    "INSERT INTO npc_allowed_user (npc_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    npc.id,
                    person.id,
                )
                self.legacy_cog._npc_access_cache[person.id].add(npc.id)
            else:
                await self.bot.db.execute(
                    "DELETE FROM npc_allowed_user WHERE npc_id = $1 AND user_id = $2",
                    npc.id,
                    person.id,
                )
                self.legacy_cog._npc_access_cache[person.id].discard(npc.id)

        message = (
            f"{config.YES} Those people can now speak as your NPC `{npc.name}`."
            if add
            else f"{config.YES} Those people can no longer speak as your NPC `{npc.name}`."
        )
        await ctx.send(message)

    async def update_automatic(
        self,
        ctx: slash_context.InteractionContext,
        *,
        npc: AccessToNPCConverter,
        channels,
        add: bool,
    ):
        if not channels:
            return await ctx.send(
                f"{config.NO} Something went wrong, you didn't specify anything.",
                ephemeral=True,
            )

        for channel in channels:
            if add:
                await self.bot.db.execute(
                    "INSERT INTO npc_automatic_mode (npc_id, user_id, channel_id, guild_id) "
                    "VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING",
                    npc.id,
                    ctx.author.id,
                    channel.id,
                    ctx.guild.id,
                )
                self.legacy_cog._automatic_npc_cache[ctx.author.id][channel.id] = npc.id
            else:
                await self.bot.db.execute(
                    "DELETE FROM npc_automatic_mode WHERE npc_id = $1 AND user_id = $2 AND channel_id = $3",
                    npc.id,
                    ctx.author.id,
                    channel.id,
                )
                self.legacy_cog._automatic_npc_cache[ctx.author.id].pop(
                    channel.id,
                    None,
                )

        message = (
            f"{config.YES} You will now automatically speak as your NPC `{npc.name}` in those channels or categories."
            if add
            else f"{config.YES} You will no longer automatically speak as your NPC `{npc.name}` in those channels or categories."
        )
        await ctx.send(message)

    @npc.command(name="about", description="Explain NPCs.")
    async def about(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="npc about")
        await ctx.defer()
        embed = text.SafeEmbed(
            description=(
                "NPCs allow you to make it look like you speak as a different character, "
                "or on behalf of someone else, like an organization or group.\n\n"
                "This can elevate the role-playing experience by making it clear "
                "when someone talks in character, or out-of-character (OOC). "
                "Political parties, newspapers, government departments or other groups can "
                "use this to release official looking announcements."
            )
        )
        embed.set_author(name="What are NPCs?", icon_url=self.bot.dciv.icon.url)
        embed.set_image(
            url="https://cdn.discordapp.com/attachments/818226072805179392/818230819835215882/npc.gif"
        )
        await ctx.send(embed=embed)

    @npc.command(name="list", description="List NPCs someone has access to.")
    async def list_npcs(
        self,
        interaction: discord.Interaction,
        member: discord.Member = None,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="npc list")
        await ctx.defer()
        member = member or ctx.author
        npc_ids = self.legacy_cog._npc_access_cache[member.id]
        records = [self.legacy_cog._npc_cache[npc_id] for npc_id in npc_ids]
        records.sort(key=lambda record: record["id"])

        entries = []
        for record in records:
            avatar = (
                f"[Avatar]({record['avatar_url']})\n" if record["avatar_url"] else ""
            )

            owner = self.bot.get_user(record["owner_id"])
            owner_value = (
                "\n"
                if not owner
                else f"Owner: {owner.mention} {escape_markdown(str(owner))}\n"
            )

            entries.append(
                f"**__NPC #{record['id']} - {escape_markdown(record['name'])}__**"
            )
            entries.append(
                f"{avatar}Trigger Phrase: `{escape_markdown(record['trigger_phrase'])}`"
            )
            entries.append(owner_value)

        if entries:
            entries.insert(
                0,
                f"You can create a new NPC with `/npc create`, "
                f"or edit the name, avatar and/or trigger phrase of an existing one with "
                f"`/npc edit <npc>`.\n",
            )

        pages = paginator.SimplePages(
            entries=entries,
            author=f"{member.display_name}'s NPCs",
            icon=member.display_avatar.url,
            per_page=20,
            empty_message="This person hasn't made any NPCs yet.",
        )
        await pages.start(ctx)

    @npc.command(name="show", description="Show details about one NPC.")
    async def show(self, interaction: discord.Interaction, npc: AnyNPCOption):
        ctx = slash_context.from_interaction(interaction, command_name="npc show")
        await ctx.defer()
        has_access = npc.id in self.legacy_cog._npc_access_cache[ctx.author.id]
        is_owner = npc.owner_id == ctx.author.id

        embed = text.SafeEmbed()

        if is_owner:
            embed.description = (
                f"You, the owner of this NPC, can edit the name, avatar and/or the trigger "
                f"phrase of this NPC with `/npc edit {npc.id}`."
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
            "SELECT user_id FROM npc_allowed_user WHERE npc_id = $1",
            npc.id,
        )
        pretty_people = []

        if is_owner:
            pretty_people.append(
                f"You, the owner of this NPC, can allow other people to speak as this NPC with "
                f"`/npc share {npc.id}`, or deny someone that you previously "
                f"allowed with `/npc unshare {npc.id}`.\n"
            )

        pretty_people.append(f"{npc.owner.mention} ({escape_markdown(str(npc.owner))})")

        for record in allowed_people:
            user = self.bot.dciv.get_member(record["user_id"]) or self.bot.get_user(
                record["user_id"]
            )
            if user:
                pretty_people.append(f"{user.mention} ({escape_markdown(str(user))})")

        embed.add_field(
            name="People with access to this NPC",
            value="\n".join(pretty_people),
            inline=False,
        )

        if ctx.guild and has_access:
            automatic_channels = await self.bot.db.fetch(
                "SELECT channel_id FROM npc_automatic_mode WHERE user_id = $1 AND guild_id = $2 AND npc_id = $3",
                ctx.author.id,
                ctx.guild.id,
                npc.id,
            )

            pretty_chan = []
            for chan in automatic_channels:
                c = ctx.guild.get_channel(chan["channel_id"])
                if c:
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

    @npc.command(name="create", description="Create a new NPC.")
    async def create(self, interaction: discord.Interaction):
        await interaction.response.send_modal(NPCFormModal(self))

    @npc.command(name="edit", description="Edit one of your NPCs.")
    async def edit(self, interaction: discord.Interaction, npc: OwnedNPCOption):
        await interaction.response.send_modal(NPCFormModal(self, npc=npc))

    @npc.command(name="delete", description="Delete one of your NPCs.")
    async def delete(self, interaction: discord.Interaction, npc: OwnedNPCOption):
        ctx = slash_context.from_interaction(interaction, command_name="npc delete")
        await ctx.defer()
        confirmed = await ui.confirm(
            ctx,
            title=f"Delete {npc.name}",
            body=f"Delete NPC #{npc.id} `{npc.name}`?",
            confirm_label="Delete",
        )
        if not confirmed:
            return await ctx.send("Cancelled.", ephemeral=True)

        await self.bot.db.execute(
            "DELETE FROM npc WHERE id = $1 AND owner_id = $2",
            npc.id,
            ctx.author.id,
        )
        await self.legacy_cog._load_npc_cache()
        await self.legacy_cog._load_automatic_trigger_cache()
        await ctx.send(f"{config.YES} `{npc.name}` was deleted.")

    @npc.command(name="share", description="Allow one person to use your NPC.")
    @app_commands.guild_only()
    async def share(
        self,
        interaction: discord.Interaction,
        npc: OwnedNPCOption,
        member: discord.Member,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="npc share")
        await ctx.defer()
        await self.update_access(ctx, npc=npc, people=[member], add=True)

    @npc.command(name="unshare", description="Remove one person's access to your NPC.")
    @app_commands.guild_only()
    async def unshare(
        self,
        interaction: discord.Interaction,
        npc: OwnedNPCOption,
        member: discord.Member,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="npc unshare")
        await ctx.defer()
        await self.update_access(ctx, npc=npc, people=[member], add=False)

    @npc.command(
        name="share-bulk", description="Allow multiple people to use your NPC."
    )
    @app_commands.guild_only()
    async def share_bulk(self, interaction: discord.Interaction, npc: OwnedNPCOption):
        await interaction.response.send_modal(NPCPeopleModal(self, npc=npc, add=True))

    @npc.command(name="unshare-bulk", description="Remove access for multiple people.")
    @app_commands.guild_only()
    async def unshare_bulk(self, interaction: discord.Interaction, npc: OwnedNPCOption):
        await interaction.response.send_modal(NPCPeopleModal(self, npc=npc, add=False))

    @npc_automatic.command(name="list", description="List your automatic NPC channels.")
    @app_commands.guild_only()
    async def automatic_list(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction, command_name="npc automatic list"
        )
        await ctx.defer()
        automatic_channels = await self.bot.db.fetch(
            "SELECT npc_automatic_mode.npc_id, npc_automatic_mode.channel_id FROM npc_automatic_mode "
            "WHERE npc_automatic_mode.user_id = $1 AND npc_automatic_mode.guild_id = $2",
            ctx.author.id,
            ctx.guild.id,
        )
        grouped_by_npc = collections.defaultdict(list)
        entries = [
            f"If you want to automatically speak as an NPC in a certain channel or channel category "
            f"without having to use the trigger phrase, use `/npc automatic enable <npc>`, "
            f"or disable it with `/npc automatic disable <npc>`.\n\nYou can only have one "
            f"automatic NPC per channel.\n\nIf you have one NPC as automatic in an entire category, "
            f"but a different NPC in a single channel that is in that same category, and you write "
            f"something in that channel, you will only speak as the NPC for that "
            f"specific channel, and not as both NPCs.\n\n"
        ]

        for record in automatic_channels:
            grouped_by_npc[record["npc_id"]].append(
                ctx.guild.get_channel(record["channel_id"])
            )

        for npc_id, channels in grouped_by_npc.items():
            npc = self.legacy_cog._npc_cache[npc_id]
            pretty_channels = [
                f"- {channel.mention if isinstance(channel, discord.TextChannel) else f'{channel.name} Category'}"
                for channel in channels
                if channel is not None
            ]
            entries.append(
                f"**__{escape_markdown(npc['name'])}__**\n" + "\n".join(pretty_channels)
            )

        if len(entries) > 1:
            pages = paginator.SimplePages(
                entries=entries,
                icon=ctx.guild_icon,
                per_page=15,
                author=f"{ctx.author.display_name}'s Automatic NPCs",
            )
            await pages.start(ctx)
        else:
            embed = text.SafeEmbed(description=entries[0])
            embed.set_author(
                name=f"{ctx.author.display_name}'s Automatic NPCs",
                icon_url=ctx.guild_icon,
            )
            await ctx.send(embed=embed)

    @npc_automatic.command(
        name="enable", description="Enable automatic mode in one channel."
    )
    @app_commands.guild_only()
    async def automatic_enable(
        self,
        interaction: discord.Interaction,
        npc: AccessNPCOption,
        channel: ChannelOption,
    ):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="npc automatic enable",
        )
        await ctx.defer()
        await self.update_automatic(ctx, npc=npc, channels=[channel], add=True)

    @npc_automatic.command(
        name="disable", description="Disable automatic mode in one channel."
    )
    @app_commands.guild_only()
    async def automatic_disable(
        self,
        interaction: discord.Interaction,
        npc: AccessNPCOption,
        channel: ChannelOption,
    ):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="npc automatic disable",
        )
        await ctx.defer()
        await self.update_automatic(ctx, npc=npc, channels=[channel], add=False)

    @npc_automatic.command(
        name="clear", description="Disable automatic mode everywhere for one NPC."
    )
    @app_commands.guild_only()
    async def automatic_clear(
        self,
        interaction: discord.Interaction,
        npc: AccessNPCOption,
    ):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="npc automatic clear",
        )
        await ctx.defer()
        channels = await self.bot.db.fetch(
            "DELETE FROM npc_automatic_mode WHERE npc_id = $1 AND user_id = $2 AND guild_id = $3 RETURNING channel_id",
            npc.id,
            ctx.author.id,
            ctx.guild.id,
        )
        for record in channels:
            self.legacy_cog._automatic_npc_cache[ctx.author.id].pop(
                record["channel_id"],
                None,
            )
        await ctx.send(
            f"{config.YES} You will no longer automatically speak as your NPC `{npc.name}` in any channel on this server.",
        )

    @npc_automatic.command(
        name="bulk-enable", description="Enable automatic mode in multiple channels."
    )
    @app_commands.guild_only()
    async def automatic_bulk_enable(
        self,
        interaction: discord.Interaction,
        npc: AccessNPCOption,
    ):
        await interaction.response.send_modal(
            NPCAutomaticChannelsModal(self, npc=npc, add=True)
        )

    @npc_automatic.command(
        name="bulk-disable", description="Disable automatic mode in multiple channels."
    )
    @app_commands.guild_only()
    async def automatic_bulk_disable(
        self,
        interaction: discord.Interaction,
        npc: AccessNPCOption,
    ):
        await interaction.response.send_modal(
            NPCAutomaticChannelsModal(self, npc=npc, add=False)
        )


async def setup(bot):
    await bot.add_cog(NPCSlash(bot))
