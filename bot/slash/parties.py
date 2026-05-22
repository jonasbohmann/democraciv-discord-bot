import re
import typing

import asyncpg
import discord
from discord import app_commands
from discord.ext import commands

from bot.config import config
from bot.slash import checks as slash_checks
from bot.slash import context as slash_context
from bot.slash import forms, transformers, ui
from bot.utils import converter, exceptions, text
from bot.utils.exceptions import ForbiddenTask

PartyOption = app_commands.Transform[
    converter.PoliticalParty,
    transformers.PoliticalPartyTransformer,
]

JOIN_MODE_OPTIONS = [
    discord.SelectOption(
        label="Public",
        value=converter.PoliticalPartyJoinMode.PUBLIC.value,
        description="Anyone can join this party.",
    ),
    discord.SelectOption(
        label="Request",
        value=converter.PoliticalPartyJoinMode.REQUEST.value,
        description="Leaders approve or deny join requests.",
    ),
    discord.SelectOption(
        label="Private",
        value=converter.PoliticalPartyJoinMode.PRIVATE.value,
        description="Only leaders can bypass the private setting.",
    ),
]


class PartyCreateModal(forms.ErrorHandledModal):
    def __init__(
        self,
        cog: "PartiesSlash",
    ):
        super().__init__(title="Create Political Party")
        self.cog = cog
        self.name = forms.text_label(
            label="Party Role Name",
            description="An existing role name will be reused; otherwise I create it.",
            max_length=100,
        )
        self.leaders = forms.text_label(
            label="Leaders",
            description="Mentions, IDs, names, or nicknames. One per line.",
            required=False,
            style=discord.TextStyle.long,
        )
        self.invite = forms.text_label(
            label="Discord Invite",
            description="Optional invite link to the party server.",
            required=False,
            max_length=512,
        )
        self.join_mode = discord.ui.Label(
            text="Join Mode",
            description="How citizens can join this party.",
            component=discord.ui.Select(options=JOIN_MODE_OPTIONS),
        )
        self.add_item(self.name)
        self.add_item(self.leaders)
        self.add_item(self.invite)
        self.add_item(self.join_mode)

    async def on_submit(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="party create")
        await ctx.defer()

        party = await self.cog.create_party(
            ctx,
            role_name=self.name.component.value,
            leaders_text=self.leaders.component.value,
            invite=self.invite.component.value,
            join_mode=self.join_mode.component.values[0],
            merge=False,
        )
        await ctx.send(
            f"{config.YES} `{party.role.name}` was added as a new Political Party.\n"
            f"{config.HINT} Add abbreviations and alternative spellings with `/party alias add`."
        )


class PartyEditModal(forms.ErrorHandledModal):
    def __init__(
        self,
        cog: "PartiesSlash",
        *,
        party: converter.PoliticalParty,
    ):
        super().__init__(title=f"Edit {ui.shorten(party.role.name, width=35)}")
        self.cog = cog
        self.party = party
        self.name = forms.text_label(
            label="Party Name",
            default=party.role.name,
            max_length=100,
        )
        self.leaders = forms.text_label(
            label="Leaders",
            description="Mentions, IDs, names, or nicknames. One per line.",
            default="\n".join(str(leader.id) for leader in party.leaders),
            required=False,
            style=discord.TextStyle.long,
        )
        self.invite = forms.text_label(
            label="Discord Invite",
            default=party.discord_invite or "",
            required=False,
            max_length=512,
        )
        join_options = []
        for option in JOIN_MODE_OPTIONS:
            join_options.append(
                discord.SelectOption(
                    label=option.label,
                    value=option.value,
                    description=option.description,
                    default=option.value == party.join_mode.value,
                )
            )

        self.join_mode = discord.ui.Label(
            text="Join Mode",
            description="How citizens can join this party.",
            component=discord.ui.Select(options=join_options),
        )
        self.add_item(self.name)
        self.add_item(self.leaders)
        self.add_item(self.invite)
        self.add_item(self.join_mode)

    async def on_submit(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="party edit")
        await ctx.defer()
        await self.cog.edit_party(
            ctx,
            party=self.party,
            new_name=self.name.component.value,
            leaders_text=self.leaders.component.value,
            invite=self.invite.component.value,
            join_mode=self.join_mode.component.values[0],
        )


class PartyMergeModal(forms.ErrorHandledModal):
    def __init__(self, cog: "PartiesSlash"):
        super().__init__(title="Merge Political Parties")
        self.cog = cog
        self.parties = forms.text_label(
            label="Parties to Merge",
            description="Party names, IDs, or aliases. One per line.",
            style=discord.TextStyle.long,
        )
        self.name = forms.text_label(
            label="New Party Role Name",
            description="An existing role name will be reused; otherwise I create it.",
            max_length=100,
        )
        self.leaders = forms.text_label(
            label="New Party Leaders",
            description="Mentions, IDs, names, or nicknames. One per line.",
            required=False,
            style=discord.TextStyle.long,
        )
        self.invite = forms.text_label(
            label="New Party Discord Invite",
            description="Optional invite link to the party server.",
            required=False,
            max_length=512,
        )
        self.join_mode = discord.ui.Label(
            text="New Party Join Mode",
            description="How citizens can join the merged party.",
            component=discord.ui.Select(options=JOIN_MODE_OPTIONS),
        )
        self.add_item(self.parties)
        self.add_item(self.name)
        self.add_item(self.leaders)
        self.add_item(self.invite)
        self.add_item(self.join_mode)

    async def on_submit(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="party merge")
        await ctx.defer(ephemeral=True)
        parties = await forms.resolve_parties(ctx, self.parties.component.value)

        if len(parties) < 2:
            return await ctx.send(
                f"{config.NO} You have to merge at least two parties.",
                ephemeral=True,
            )

        pretty = ", ".join(f"`{party.role.name}`" for party in parties)
        confirmed = await ui.confirm(
            ctx,
            title="Merge Parties",
            body=f"Merge {pretty} into one party?",
            confirm_label="Continue",
        )

        if not confirmed:
            return await ctx.send("Cancelled.", ephemeral=True)

        new_party = await self.cog.create_party(
            ctx,
            role_name=self.name.component.value,
            leaders_text=self.leaders.component.value,
            invite=self.invite.component.value,
            join_mode=self.join_mode.component.values[0],
            merge=True,
        )
        await self.cog.finish_merge(ctx, new_party=new_party, old_parties=parties)


class PartiesSlash(commands.Cog):
    party = app_commands.Group(
        name="party",
        description="Show, join, and manage political parties.",
        guild_only=True,
    )
    party_alias = app_commands.Group(
        name="alias",
        description="Manage political party aliases.",
        parent=party,
    )

    def __init__(self, bot):
        self.bot = bot
        self.discord_invite_pattern = re.compile(
            r"(?:https?://)?discord(?:app\.com/invite|\.gg)/?[a-zA-Z0-9]+/?"
        )

    def normalize_invite(self, value: str) -> typing.Optional[str]:
        value = (value or "").strip()
        if value and self.discord_invite_pattern.fullmatch(value):
            return value

        return None

    async def find_or_create_role(
        self,
        ctx: slash_context.InteractionContext,
        name: str,
    ) -> discord.Role:
        arg = (name or "").strip()
        if not arg:
            raise exceptions.DemocracivBotException(
                f"{config.NO} The party name cannot be empty."
            )

        role = discord.utils.find(
            lambda candidate: candidate.name.lower() == arg.lower(),
            self.bot.dciv.roles,
        )
        if role is not None:
            return role

        try:
            return await self.bot.dciv.create_role(name=arg)
        except discord.Forbidden:
            raise exceptions.ForbiddenError(exceptions.ForbiddenTask.CREATE_ROLE, arg)

    async def create_party(
        self,
        ctx: slash_context.InteractionContext,
        *,
        role_name: str,
        leaders_text: str,
        invite: str,
        join_mode: str,
        merge: bool = False,
    ) -> converter.PoliticalParty:
        role = await self.find_or_create_role(ctx, role_name)

        try:
            existing = await converter.PoliticalParty.convert(ctx, role.id)
        except exceptions.NotFoundError:
            existing = None

        if merge and existing is not None:
            return existing

        if not merge and existing is not None:
            raise exceptions.DemocracivBotException(
                f"{config.NO} `{role.name}` already is a political party."
            )

        leaders = await forms.resolve_members(ctx, leaders_text)
        leader_ids = [leader.id for leader in leaders] or [0]
        invite = self.normalize_invite(invite)

        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                try:
                    await connection.execute(
                        "INSERT INTO party (id, discord_invite, join_mode) VALUES ($1, $2, $3)"
                        "ON CONFLICT (id) DO UPDATE SET discord_invite = $2, join_mode = $3 WHERE party.id = $1",
                        role.id,
                        invite,
                        join_mode,
                    )
                except asyncpg.UniqueViolationError:
                    raise exceptions.DemocracivBotException(
                        f"{config.NO} `{role.name}` already is a political party."
                    )

                await connection.execute(
                    "INSERT INTO party_alias (party_id, alias) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    role.id,
                    role.name.lower(),
                )

                for leader_id in leader_ids:
                    await connection.execute(
                        "INSERT INTO party_leader (party_id, leader_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                        role.id,
                        leader_id,
                    )

        return await converter.PoliticalParty.convert(ctx, role.id)

    async def edit_party(
        self,
        ctx: slash_context.InteractionContext,
        *,
        party: converter.PoliticalParty,
        new_name: str,
        leaders_text: str,
        invite: str,
        join_mode: str,
    ):
        if party.is_independent:
            return await ctx.send(
                f"{config.NO} You can't change the Independent party.",
                ephemeral=True,
            )

        new_name = (new_name or "").strip()
        if not new_name:
            return await ctx.send(
                f"{config.NO} Party names cannot be empty.", ephemeral=True
            )

        if party.role.name != new_name:
            try:
                other = await converter.PoliticalParty.convert(ctx, new_name)
            except exceptions.NotFoundError:
                other = None

            if other is not None and other._id != party._id:
                return await ctx.send(
                    f"{config.NO} Another political party is already named `{new_name}`.",
                    ephemeral=True,
                )

            old_name = party.role.name
            await party.role.edit(name=new_name)
            async with self.bot.db.acquire() as connection:
                async with connection.transaction():
                    await connection.execute(
                        "DELETE FROM party_alias WHERE alias = $1",
                        old_name.lower(),
                    )
                    await connection.execute(
                        "INSERT INTO party_alias (alias, party_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                        new_name.lower(),
                        party.role.id,
                    )

        leaders = await forms.resolve_members(ctx, leaders_text)
        leader_ids = [leader.id for leader in leaders] or [0]
        invite = self.normalize_invite(invite)

        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "UPDATE party SET discord_invite = $2, join_mode = $3 WHERE id = $1",
                    party.role.id,
                    invite,
                    join_mode,
                )
                await connection.execute(
                    "DELETE FROM party_leader WHERE party_id = $1",
                    party.role.id,
                )
                for leader_id in leader_ids:
                    await connection.execute(
                        "INSERT INTO party_leader (party_id, leader_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                        party.role.id,
                        leader_id,
                    )

        await ctx.send(f"{config.YES} `{new_name}` was edited.")

    async def finish_merge(
        self,
        ctx: slash_context.InteractionContext,
        *,
        new_party: converter.PoliticalParty,
        old_parties: typing.Sequence[converter.PoliticalParty],
    ):
        members_to_merge = set()
        for party in old_parties:
            if party.role is not None:
                members_to_merge.update(party.role.members)

        for member in members_to_merge:
            try:
                await member.add_roles(new_party.role)
            except discord.Forbidden:
                raise exceptions.ForbiddenError(
                    ForbiddenTask.ADD_ROLE,
                    new_party.role.name,
                )

        for party in old_parties:
            if party.role.id == new_party.role.id:
                continue

            async with self.bot.db.acquire() as connection:
                async with connection.transaction():
                    await connection.execute(
                        "DELETE FROM party WHERE id = $1", party.role.id
                    )
                    await connection.execute(
                        "DELETE FROM party_alias WHERE party_id = $1",
                        party.role.id,
                    )
                    await connection.execute(
                        "DELETE FROM party_leader WHERE party_id = $1",
                        party.role.id,
                    )

            try:
                await party.role.delete()
            except discord.Forbidden:
                raise exceptions.ForbiddenError(
                    ForbiddenTask.DELETE_ROLE,
                    detail=party.role.name,
                )

        await ctx.send(
            f"{config.YES} The old parties were deleted and all their members now have the role of `{new_party.role.name}`."
        )

    async def party_entries(self):
        parties_and_members = []

        for record in await self.bot.db.fetch("SELECT id FROM party"):
            role = self.bot.dciv.get_role(record["id"])
            if role is not None:
                parties_and_members.append((role.name, len(role.members)))

        parties_and_members.sort(key=lambda row: row[1], reverse=True)
        return parties_and_members

    @party.command(name="list", description="List political parties by member count.")
    async def list_parties(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="party list")
        await ctx.defer()

        entries = []
        independent_role = discord.utils.get(self.bot.dciv.roles, name="Independent")

        for party_name, member_count in await self.party_entries():
            if party_name == "Independent":
                continue

            entries.append(
                f"**{party_name}**\n{member_count} member{'s' if member_count != 1 else ''}"
            )

        if independent_role:
            entries.append(
                f"**Independent**\n{len(independent_role.members)} citizen"
                f"{'s' if len(independent_role.members) != 1 else ''}"
            )

        await ui.send_pages(
            ctx,
            entries=entries,
            title=f"Political Parties in {self.bot.mk.NATION_NAME}",
            subtitle=f"-# Check out [party platforms and descriptions]({self.bot.mk.POLITICAL_PARTIES}).",
            empty_message="There are no political parties yet.",
            per_page=12,
            links=[
                ui.LayoutLink("Platforms", self.bot.mk.POLITICAL_PARTIES, "\U0001f4dc")
            ],
        )

    @party.command(name="show", description="Show details about one political party.")
    async def show_party(self, interaction: discord.Interaction, party: PartyOption):
        ctx = slash_context.from_interaction(interaction, command_name="party show")
        await ctx.defer()

        if not party.role:
            return await ctx.send(f"{config.NO} That party's role no longer exists.")

        sections = []

        if not party.is_independent:
            sections.extend(
                [
                    ui.LayoutSection(
                        "Overview",
                        f"[Platform and Description]({self.bot.mk.POLITICAL_PARTIES})\n"
                        f"Join this party with `/party join`.",
                    ),
                    ui.LayoutSection(
                        "Join Setting",
                        party.join_mode.value,
                    ),
                    ui.LayoutSection(
                        "Discord Server",
                        party.discord_invite or "*N/A*",
                    ),
                    ui.LayoutSection(
                        "Aliases",
                        "\n".join(
                            f"`{alias}`"
                            for alias in party.aliases
                            if alias != party.role.name.lower()
                        )
                        or "-",
                    ),
                ]
            )
        else:
            sections.append(
                ui.LayoutSection(
                    "Overview",
                    "Independents are citizens who are not part of a political party.",
                )
            )

        members = []
        party_members = [
            member.display_name
            for member in party.role.members
            if member.id not in party.leader_ids
        ]
        for index, leader in enumerate(party.leaders):
            if leader in party.role.members:
                party_members.insert(index, f"**{leader.display_name}**")

        for member in party_members:
            members.append(f"* {member}")

        sections.append(
            ui.LayoutSection(
                f"Members ({len(party.role.members)})",
                "\n".join(members) or "-",
            )
        )

        await ui.send_static(
            ctx,
            title=party.role.name,
            sections=sections,
            links=[
                ui.LayoutLink("Platforms", self.bot.mk.POLITICAL_PARTIES, "\U0001f4dc")
            ],
        )

    @party.command(name="join", description="Join a political party.")
    @slash_checks.is_citizen_if_multiciv()
    async def join_party(self, interaction: discord.Interaction, party: PartyOption):
        ctx = slash_context.from_interaction(interaction, command_name="party join")
        await ctx.defer()

        person_in_dciv = self.bot.dciv.get_member(ctx.author.id)
        if person_in_dciv is None:
            return await ctx.send(
                f"{config.NO} You're not in the {self.bot.dciv.name} server.",
                ephemeral=True,
            )

        if party.role in person_in_dciv.roles:
            return await ctx.send(
                f"{config.NO} You're already part of `{party.role.name}`.",
                ephemeral=True,
            )

        if party.join_mode is converter.PoliticalPartyJoinMode.PRIVATE:
            if person_in_dciv in party.leaders:
                try:
                    await person_in_dciv.add_roles(party.role)
                except discord.Forbidden:
                    raise exceptions.ForbiddenError(
                        ForbiddenTask.ADD_ROLE, party.role.name
                    )

                return await ctx.send(
                    f"{config.YES} You joined {party.role.name}.\n{config.HINT} "
                    f"*As you're a leader of this party, you ignored this party's join mode of `Private`.*",
                )

            return await ctx.send(
                f"{config.NO} {party.role.name} is a private party. Contact the party leaders for further information.",
                ephemeral=True,
            )

        if party.join_mode is converter.PoliticalPartyJoinMode.REQUEST:
            if person_in_dciv in party.leaders:
                try:
                    await person_in_dciv.add_roles(party.role)
                except discord.Forbidden:
                    raise exceptions.ForbiddenError(
                        ForbiddenTask.ADD_ROLE, party.role.name
                    )

                return await ctx.send(
                    f"{config.YES} You joined {party.role.name}.\n{config.HINT} "
                    f"*As you're a leader of this party, you skipped the request step.*",
                )

            existing_request = await self.bot.db.fetchrow(
                "SELECT * FROM party_join_request WHERE party_id = $1 AND requesting_member = $2",
                party.role.id,
                ctx.author.id,
            )
            if existing_request:
                return await ctx.send(
                    f"{config.NO} You already requested to join `{party.role.name}`. Once the leaders accept or deny your request, I will notify you.",
                    ephemeral=True,
                )

            if not party.leaders:
                return await ctx.send(
                    f"{config.NO} I was not told who `{party.role.name}`'s leaders are.",
                    ephemeral=True,
                )

            request_id = await self.bot.db.fetchval(
                "INSERT INTO party_join_request (party_id, requesting_member) VALUES ($1, $2) RETURNING id",
                party.role.id,
                ctx.author.id,
            )
            leaders_fmt = ", ".join(f"`{leader}`" for leader in party.leaders)
            await ctx.send(
                f"{config.YES} Your request to join `{party.role.name}` was sent to their leaders ({leaders_fmt}). "
                f"Once they accept or deny your request, I'll notify you.",
            )

            for leader in party.leaders:
                try:
                    other_leaders = [
                        candidate
                        for candidate in party.leaders
                        if candidate.id != leader.id
                    ]
                    other_help = ""
                    if other_leaders:
                        other_help = (
                            "\nThe other party leaders, "
                            + ", ".join(f"`{other}`" for other in other_leaders)
                            + ", also received this message. Once any of you either accept or deny, that is the final decision."
                        )

                    embed = text.SafeEmbed(
                        title=f"Request to join {party.role.name}",
                        description=(
                            f"{ctx.author.display_name} wants to join your political party "
                            f"**{party.role.name}**. Do you want to accept their request?\n\n"
                            f"{config.HINT} This has no timeout, so you don't have to decide immediately."
                            f"{other_help}"
                        ),
                    )
                    embed.set_author(name=ctx.author, icon_url=ctx.author_icon)
                    message = await leader.send(embed=embed)
                    await message.add_reaction(config.YES)
                    await message.add_reaction(config.NO)
                except discord.Forbidden:
                    continue

                await self.bot.db.execute(
                    "INSERT INTO party_join_request_message (request_id, message_id) VALUES ($1, $2)",
                    request_id,
                    message.id,
                )

            return

        try:
            await person_in_dciv.add_roles(party.role)
        except discord.Forbidden:
            raise exceptions.ForbiddenError(ForbiddenTask.ADD_ROLE, party.role.name)

        if party.role.name == "Independent":
            return await ctx.send(
                f"{config.YES} You are now an {party.role.name}.",
            )

        message = f"{config.YES} You've joined {party.role.name}."
        if party.discord_invite:
            message = f"{message} Now head to their Discord Server and introduce yourself: {party.discord_invite}"

        await ctx.send(message)

    @party.command(name="leave", description="Leave a political party.")
    @slash_checks.is_citizen_if_multiciv()
    async def leave_party(self, interaction: discord.Interaction, party: PartyOption):
        ctx = slash_context.from_interaction(interaction, command_name="party leave")
        await ctx.defer()

        person_in_dciv = self.bot.dciv.get_member(ctx.author.id)
        if person_in_dciv is None:
            return await ctx.send(
                f"{config.NO} You're not in the {self.bot.dciv.name} server.",
                ephemeral=True,
            )

        if party.role not in person_in_dciv.roles:
            return await ctx.send(
                f"{config.NO} You are not part of {party.role.name}.",
                ephemeral=True,
            )

        try:
            await person_in_dciv.remove_roles(party.role)
        except discord.Forbidden:
            raise exceptions.ForbiddenError(
                ForbiddenTask.REMOVE_ROLE,
                detail=party.role.name,
            )

        article = "an " if party.role.name == "Independent" else ""
        verb = "are no longer" if party.role.name == "Independent" else "left"
        await ctx.send(
            f"{config.YES} You {verb} {article}{party.role.name}.",
        )

    @party.command(name="create", description="Create a political party.")
    @slash_checks.moderation_or_nation_leader()
    @slash_checks.bot_has_guild_permissions(manage_roles=True)
    async def create_party_command(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PartyCreateModal(self))

    @party.command(name="edit", description="Edit a political party.")
    @slash_checks.moderation_or_nation_leader()
    @slash_checks.bot_has_guild_permissions(manage_roles=True)
    async def edit_party_command(
        self,
        interaction: discord.Interaction,
        party: PartyOption,
    ):
        await interaction.response.send_modal(PartyEditModal(self, party=party))

    @party.command(name="delete", description="Delete a political party.")
    @slash_checks.moderation_or_nation_leader()
    @slash_checks.bot_has_guild_permissions(manage_roles=True)
    async def delete_party(
        self,
        interaction: discord.Interaction,
        party: PartyOption,
        also_delete_discord_role: bool = False,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="party delete")
        await ctx.defer(ephemeral=True)

        confirmed = await ui.confirm(
            ctx,
            title=f"Delete {party.role.name}",
            body=(
                f"Remove `{party.role.name}` from the list of parties"
                + (
                    " and delete their Discord role too?"
                    if also_delete_discord_role
                    else "?"
                )
            ),
            confirm_label="Delete",
        )
        if not confirmed:
            return await ctx.send("Cancelled.", ephemeral=True)

        name = party.role.name
        async with self.bot.db.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "DELETE FROM party_alias WHERE party_id = $1",
                    party.role.id,
                )
                await connection.execute(
                    "DELETE FROM party_leader WHERE party_id = $1",
                    party.role.id,
                )
                await connection.execute(
                    "DELETE FROM party WHERE id = $1", party.role.id
                )

        if also_delete_discord_role and party.role:
            try:
                await party.role.delete()
            except discord.Forbidden:
                raise exceptions.ForbiddenError(
                    ForbiddenTask.DELETE_ROLE,
                    detail=party.role.name,
                )

        await ctx.send(f"{config.YES} `{name}` and all its aliases were deleted.")

    @party.command(name="merge", description="Merge multiple parties into one.")
    @slash_checks.moderation_or_nation_leader()
    @slash_checks.bot_has_guild_permissions(manage_roles=True)
    async def merge_parties(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PartyMergeModal(self))

    @party_alias.command(name="add", description="Add an alias to a political party.")
    @slash_checks.moderation_or_nation_leader()
    async def add_alias(
        self,
        interaction: discord.Interaction,
        party: PartyOption,
        alias: str,
    ):
        ctx = slash_context.from_interaction(
            interaction, command_name="party alias add"
        )
        await ctx.defer(ephemeral=True)
        alias = alias.lower().strip()

        try:
            await self.bot.db.execute(
                "INSERT INTO party_alias (alias, party_id) VALUES ($1, $2)",
                alias,
                party.role.id,
            )
        except asyncpg.UniqueViolationError:
            return await ctx.send(
                f"{config.NO} `{alias}` is already an alias for `{party.role.name}`.",
                ephemeral=True,
            )

        await ctx.send(
            f"{config.YES} Alias `{alias}` for party `{party.role.name}` was added.",
            ephemeral=True,
        )

    @party_alias.command(name="remove", description="Remove one political party alias.")
    @slash_checks.moderation_or_nation_leader()
    async def remove_alias(self, interaction: discord.Interaction, alias: str):
        ctx = slash_context.from_interaction(
            interaction, command_name="party alias remove"
        )
        await ctx.defer(ephemeral=True)
        alias = alias.lower().strip()

        try:
            await converter.PoliticalParty.convert(ctx, alias)
        except exceptions.NotFoundError:
            return await ctx.send(
                f"{config.NO} `{alias}` is not an alias of any party.",
                ephemeral=True,
            )

        await self.bot.db.execute("DELETE FROM party_alias WHERE alias = $1", alias)
        await ctx.send(f"{config.YES} Alias `{alias}` was deleted.", ephemeral=True)

    @party_alias.command(name="clear", description="Remove all aliases from a party.")
    @slash_checks.moderation_or_nation_leader()
    async def clear_aliases(
        self,
        interaction: discord.Interaction,
        party: PartyOption,
    ):
        ctx = slash_context.from_interaction(
            interaction, command_name="party alias clear"
        )
        await ctx.defer(ephemeral=True)

        confirmed = await ui.confirm(
            ctx,
            title=f"Clear aliases for {party.role.name}",
            body=f"Delete all aliases of `{party.role.name}` except the party's own name?",
            confirm_label="Clear",
        )
        if not confirmed:
            return await ctx.send("Cancelled.", ephemeral=True)

        for alias in party.aliases:
            if alias == party.role.name.lower():
                continue
            await self.bot.db.execute("DELETE FROM party_alias WHERE alias = $1", alias)

        await ctx.send(
            f"{config.YES} All aliases of `{party.role.name}` were deleted.",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(PartiesSlash(bot))
