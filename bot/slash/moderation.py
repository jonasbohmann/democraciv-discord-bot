import discord
from discord import app_commands
from discord.ext import commands

from bot.config import config, mk, token
from bot.slash import checks as slash_checks
from bot.slash import context as slash_context
from bot.slash import forms, ui
from bot.utils import exceptions
from bot.utils.exceptions import ForbiddenTask


class ReportModal(forms.ErrorHandledModal):
    def __init__(self, cog: "ModerationSlash"):
        super().__init__(title="Report to Moderation")
        self.cog = cog
        self.content = forms.text_label(
            label="Report Details",
            description="Abuse or spam reports may be punished.",
            max_length=2048,
            style=discord.TextStyle.long,
        )
        self.anonymous = forms.checkbox_label(
            label="Anonymous Report",
            description="Hide your Discord name from the report.",
            default=False,
        )
        self.add_item(self.content)
        self.add_item(self.anonymous)

    async def on_submit(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="report")
        await ctx.defer(ephemeral=True)
        await self.cog.send_report(
            ctx,
            content=self.content.component.value,
            anonymous=self.anonymous.component.value,
        )


class ModerationSlash(commands.Cog):
    moderation = app_commands.Group(
        name="moderation",
        description="Moderation links and tools.",
        guild_only=True,
    )

    def __init__(self, bot):
        self.bot = bot

    async def send_report(
        self,
        ctx: slash_context.InteractionContext,
        *,
        content: str,
        anonymous: bool,
    ):
        embed = discord.Embed(
            title=":exclamation: New Report",
            description=content,
            colour=config.BOT_EMBED_COLOUR,
        )
        embed.add_field(
            name="From",
            value="*Anonymous Report*" if anonymous else str(ctx.author),
        )

        await self.bot.get_democraciv_channel(
            mk.DemocracivChannel.MODERATION_NOTIFICATIONS_CHANNEL
        ).send(
            content=self.bot.get_democraciv_role(mk.DemocracivRole.MODERATION).mention,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(roles=True),
        )
        await ctx.send(f"{config.YES} Report was sent.", ephemeral=True)

    async def send_mod_link(
        self,
        ctx: slash_context.InteractionContext,
        *,
        title: str,
        url: str,
    ):
        url = url or "https://hastebin.com/afijavahox.coffeescript"
        unsafe = True
        if isinstance(ctx.channel, discord.TextChannel):
            unsafe_members = [
                member
                for member in ctx.channel.members
                if not member.bot and not member.guild_permissions.administrator
            ]
            unsafe = len(ctx.channel.members) >= 20 or bool(unsafe_members)

        await ctx.send(
            view=ui.RichLayout(
                title=title,
                links=[ui.LayoutLink("Open", url, "\U0001f517")],
                author_id=ctx.author.id,
            ),
            ephemeral=unsafe,
        )

    def can_act_on_member(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        *,
        action: str,
    ):
        actor = interaction.user
        if not isinstance(actor, discord.Member):
            raise app_commands.NoPrivateMessage()

        if member.id == actor.id:
            return f"{config.NO} You can't {action} yourself."

        owner = getattr(self.bot, "owner", None)
        if owner and member.id == owner.id:
            raise exceptions.ForbiddenError(
                ForbiddenTask.MEMBER_BAN
                if action == "ban"
                else ForbiddenTask.MEMBER_KICK
            )

        if interaction.guild and member.id == interaction.guild.me.id:
            return f"{config.NO} I can't {action} myself."

        if member.top_role >= actor.top_role:
            return f"{config.NO} You aren't allowed to {action} someone with a higher role than yours."

    @app_commands.command(
        name="report", description="Report something to Democraciv Moderation."
    )
    async def report(self, interaction: discord.Interaction):
        if interaction.guild is not None:
            return await interaction.response.send_message(
                f"{config.NO} This command can only be used in DMs with me.",
                ephemeral=True,
            )

        await interaction.response.send_modal(ReportModal(self))

    @app_commands.command(
        name="say", description="Make the bot say something in this channel."
    )
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def say(self, interaction: discord.Interaction, content: str):
        ctx = slash_context.from_interaction(interaction, command_name="say")
        await ctx.send(content)

    @moderation.command(name="hub", description="Link to the Moderation Hub.")
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def hub(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="moderation hub")
        await self.send_mod_link(ctx, title="Moderation Hub", url=token.MOD_HUB)

    @moderation.command(name="registry", description="Link to the Democraciv Registry.")
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def registry(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction, command_name="moderation registry"
        )
        await self.send_mod_link(ctx, title="Democraciv Registry", url=token.REGISTRY)

    @moderation.command(
        name="drive", description="Link to the Moderation Google Drive."
    )
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def drive(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction, command_name="moderation drive"
        )
        await self.send_mod_link(
            ctx, title="Moderation Google Drive", url=token.MOD_DRIVE
        )

    @moderation.command(name="pin", description="Link to the election tool.")
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def pin(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="moderation pin")
        await self.send_mod_link(
            ctx, title="DerJonas' Election Tool", url=token.PIN_TOOL
        )

    @moderation.command(name="guidelines", description="Link to moderation guidelines.")
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def guidelines(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="moderation guidelines",
        )
        await self.send_mod_link(
            ctx,
            title="DerJonas' Democraciv Moderation Guidelines & Procedures",
            url=token.MOD_GUIDELINES,
        )

    @moderation.command(name="quire", description="Link to Quire project management.")
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def quire(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(
            interaction, command_name="moderation quire"
        )
        await self.send_mod_link(
            ctx,
            title="Quire",
            url="https://quire.io/c/democraciv-moderation",
        )

    @app_commands.command(name="kick", description="Kick one member.")
    @app_commands.guild_only()
    @slash_checks.has_guild_permissions(kick_members=True)
    @slash_checks.bot_has_guild_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member):
        ctx = slash_context.from_interaction(interaction, command_name="kick")
        await ctx.defer()
        failed = self.can_act_on_member(interaction, member, action="kick")
        if failed:
            return await ctx.send(failed, ephemeral=True)

        await self.bot.safe_send_dm(
            target=member,
            reason="ban_kick_mute",
            message=f":boot: You were **kicked** from {ctx.guild.name}.",
        )
        try:
            await ctx.guild.kick(
                member,
                reason=f"Action requested by {ctx.author} ({ctx.author.id}).",
            )
        except discord.Forbidden:
            raise exceptions.ForbiddenError(ForbiddenTask.MEMBER_KICK)

        await ctx.send(f"{config.YES} {member} was kicked.")

    @app_commands.command(
        name="clear", description="Purge messages in the current channel."
    )
    @app_commands.guild_only()
    @slash_checks.has_guild_permissions(manage_messages=True)
    @slash_checks.bot_has_guild_permissions(manage_messages=True)
    async def clear(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 500],
        target: discord.User = None,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="clear")
        await ctx.defer()

        def check(message):
            if target:
                return message.author.id == target.id
            return True

        try:
            deleted = await ctx.channel.purge(limit=amount, check=check)
        except discord.Forbidden:
            raise exceptions.ForbiddenError(task=ForbiddenTask.MESSAGE_DELETE)

        await ctx.send(f"{config.YES} Deleted **{len(deleted)}** messages.")

    @app_commands.command(name="ban", description="Ban a user or user ID.")
    @app_commands.guild_only()
    @slash_checks.has_guild_permissions(ban_members=True)
    @slash_checks.bot_has_guild_permissions(ban_members=True)
    async def ban(
        self,
        interaction: discord.Interaction,
        user: discord.User = None,
        user_id: str = None,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="ban")
        await ctx.defer()
        if user is None and not user_id:
            return await ctx.send(
                f"{config.NO} Provide either a user or a user ID.",
                ephemeral=True,
            )

        member_object = user
        try:
            member_id = user.id if user else int(user_id)
        except ValueError:
            return await ctx.send(
                f"{config.NO} I couldn't find that person.", ephemeral=True
            )
        if member_id == ctx.author.id:
            return await ctx.send(
                f"{config.NO} You can't ban yourself.", ephemeral=True
            )

        owner = getattr(self.bot, "owner", None)
        if owner and member_id == owner.id:
            raise exceptions.ForbiddenError(ForbiddenTask.MEMBER_BAN)

        if member_id == ctx.guild.me.id:
            return await ctx.send(f"{config.NO} I can't ban myself.", ephemeral=True)

        if isinstance(user, discord.Member):
            failed = self.can_act_on_member(interaction, user, action="ban")
            if failed:
                return await ctx.send(failed, ephemeral=True)

            await self.bot.safe_send_dm(
                target=user,
                reason="ban_kick_mute",
                message=f":no_entry: You were **banned** from {ctx.guild.name}.",
            )

        try:
            await ctx.guild.ban(
                discord.Object(id=member_id),
                reason=f"Action requested by {ctx.author} ({ctx.author.id}).",
                delete_message_days=0,
            )
        except discord.Forbidden:
            raise exceptions.ForbiddenError(ForbiddenTask.MEMBER_BAN)
        except discord.HTTPException:
            return await ctx.send(
                f"{config.NO} I couldn't find that person.", ephemeral=True
            )

        name = (
            str(member_object)
            if member_object
            else f"The Discord user with ID `{member_id}`"
        )
        await ctx.send(f"{config.YES} {name} was banned.")

    @app_commands.command(name="unban", description="Unban a user ID.")
    @app_commands.guild_only()
    @slash_checks.has_guild_permissions(ban_members=True)
    @slash_checks.bot_has_guild_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str):
        ctx = slash_context.from_interaction(interaction, command_name="unban")
        await ctx.defer()
        try:
            user_id_int = int(user_id)
        except ValueError:
            return await ctx.send(
                f"{config.NO} I couldn't find that person.", ephemeral=True
            )

        try:
            await ctx.guild.unban(
                discord.Object(id=user_id_int),
                reason=f"Action requested by {ctx.author} ({ctx.author.id}).",
            )
        except discord.Forbidden:
            raise exceptions.ForbiddenError(ForbiddenTask.MEMBER_BAN)
        except discord.HTTPException:
            return await ctx.send(
                f"{config.NO} That person is not banned.", ephemeral=True
            )

        await ctx.send(
            f"{config.YES} The Discord user with ID `{user_id_int}` was unbanned."
        )

    async def archive_channel_impl(
        self,
        ctx: slash_context.InteractionContext,
        *,
        channel: discord.TextChannel,
        archive_category: discord.CategoryChannel,
    ):
        archives_role = discord.utils.get(self.bot.dciv.roles, name="Archives")
        if archives_role is None:
            return await ctx.send(
                f"{config.NO} There is no role named `Archives` for me to use.",
                ephemeral=True,
            )

        everyone_perms = discord.PermissionOverwrite(
            read_message_history=False,
            send_messages=False,
            read_messages=False,
            add_reactions=False,
        )
        archive_perms = discord.PermissionOverwrite(
            read_message_history=True,
            send_messages=False,
            read_messages=True,
            add_reactions=False,
        )
        await channel.edit(
            name=(
                f"mk{self.bot.mk.MARK}-{channel.name}"
                if not channel.name.startswith(f"mk{self.bot.mk.MARK}-")
                else channel.name
            ),
            overwrites={
                self.bot.dciv.default_role: everyone_perms,
                archives_role: archive_perms,
            },
            category=archive_category,
        )
        await self.bot.db.execute(
            "DELETE FROM guild_private_channel WHERE guild_id = $1 AND channel_id = $2",
            channel.guild.id,
            channel.id,
        )

    @moderation.command(name="archive-channel", description="Archive one channel.")
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def archive_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        archive_category: discord.CategoryChannel,
    ):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="moderation archive-channel",
        )
        await ctx.defer()
        await self.archive_channel_impl(
            ctx,
            channel=channel,
            archive_category=archive_category,
        )
        await ctx.send(f"{config.YES} Channel was archived.")

    @moderation.command(
        name="archive-category", description="Archive every text channel in a category."
    )
    @slash_checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def archive_category(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        archive_category: discord.CategoryChannel,
    ):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="moderation archive-category",
        )
        await ctx.defer()
        confirmed = await ui.confirm(
            ctx,
            title=f"Archive {category.name}",
            body=f"Archive every channel in `{category}`?",
            confirm_label="Archive",
        )
        if not confirmed:
            return await ctx.send("Cancelled.", ephemeral=True)

        for channel in category.text_channels:
            await channel.send(
                f":tada: Thanks for playing Democraciv MK{self.bot.mk.MARK}!"
            )
            await self.archive_channel_impl(
                ctx,
                channel=channel,
                archive_category=archive_category,
            )

        await ctx.send(f"{config.YES} Done.")


async def setup(bot):
    await bot.add_cog(ModerationSlash(bot))
