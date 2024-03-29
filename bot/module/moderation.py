import discord

from discord.ext import commands
from bot.utils import exceptions, text, context, checks, converter
from bot.config import token, config, mk
from bot.utils.exceptions import ForbiddenTask
from bot.utils.converter import (
    UnbanConverter,
    BanConverter,
    CaseInsensitiveMember,
    CaseInsensitiveUser,
    CaseInsensitiveTextChannel,
    CaseInsensitiveCategoryChannel,
    Fuzzy,
    FuzzySettings,
)


class Moderation(context.CustomCog):
    """Commands for the Mod Team of this server"""

    async def calculate_alt_chance(self, member: discord.Member) -> (int, str):
        is_alt_chance = 0
        factor_details = ""

        if member.bot:
            return 0, "Bot Account (0%)"

        # Check how long it has been since the user registered
        discord_registration_duration_in_s = (
            discord.utils.utcnow() - member.created_at
        ).total_seconds()
        hours_since = divmod(discord_registration_duration_in_s, 3600)[0]

        if hours_since <= 48:
            # If the account is new, check if the they bothered to change the default avatar
            is_alt_chance += 0.1
            factor_details += "Less than 48 hours since registration (+10%)\n"
            if member.avatar is None:
                is_alt_chance += 0.55
                factor_details += "Default avatar (+55%)\n"
            if hours_since <= 24:
                is_alt_chance += 0.2
                factor_details += "Less than 24 hours since registration (+20%)\n"
                if hours_since <= 12:
                    is_alt_chance += 0.25
                    factor_details += "Less than 12 hours since registration (+25%)\n"
                    if hours_since <= 1:
                        is_alt_chance += 0.35
                        factor_details += "Less than 1 hour since registration (+35%)\n"

        weird_names = [
            "alt",
            "mysterious",
            "anonymous",
            "anon",
            "banned",
            "ban",
            "das",
            "mysterybox",
            "not",
            "definitelynot",
            "darthspectrum",
        ]

        if any(name in member.name.lower() for name in weird_names) or any(
            name in member.display_name.lower() for name in weird_names
        ):
            # Check if user has any names that are associated with alt accounts in the past
            is_alt_chance += 0.45
            factor_details += "Suspicious username (+45%)\n"

        if member.status != discord.Status.offline:
            # If the user didn't download a Discord App, but is accessing Discord through their browser, chances
            # increase that they're an alt
            if (
                isinstance(member.web_status, discord.Status)
                and member.web_status != discord.Status.offline
            ):
                factor_details += "Uses Discord Web instead of apps (+5%)\n"
                is_alt_chance += 0.05

        if member.premium_since is not None:
            # If user has Nitro (boosted this guild), it's likely not an alt
            factor_details += "Discord Nitro (-200%)\n"
            is_alt_chance -= 2

        if len(member.activities) > 0:
            # Check for linked Twitch & Spotify accounts or if user is playing a game
            for act in member.activities:
                if act.type != 4:  # Custom Status
                    is_alt_chance -= 1.5
                    factor_details += "Game, Twitch or Spotify connection (-150%)\n"
                    break

        if member.is_avatar_animated():
            # If user has Nitro (with animated profile picture), it's likely not an alt
            is_alt_chance -= 2
            factor_details += "Discord Nitro (-200%)\n"

        return is_alt_chance, factor_details

    @commands.Cog.listener(name="on_message")
    async def mod_request_listener(self, message):
        # If it's a command, ignore
        if (await self.bot.get_context(message)).valid:
            return

        if message.guild != self.bot.dciv:
            return

        if message.author.bot:
            return

        try:
            mod_role = self.bot.get_democraciv_role(mk.DemocracivRole.MODERATION)
        except exceptions.RoleNotFoundError:
            return

        if mod_role is None:
            return

        try:
            mod_channel = self.bot.get_democraciv_channel(
                mk.DemocracivChannel.MODERATION_NOTIFICATIONS_CHANNEL
            )
        except exceptions.ChannelNotFoundError:
            return

        if mod_role in message.role_mentions:
            embed = text.SafeEmbed(
                title=f":pushpin:  New Request in #{message.channel.name}",
                description=message.content,
            )
            embed.add_field(name="From", value=message.author.mention)
            embed.add_field(
                name="Original", value=f"[Jump to Message]({message.jump_url})"
            )
            await mod_channel.send(embed=embed)

    @commands.Cog.listener(name="on_member_join")
    async def possible_alt_listener(self, member):
        if member.guild != self.bot.dciv:
            return

        if member.bot:
            return

        chance, details = await self.calculate_alt_chance(member)

        if chance >= 0.2:
            embed = text.SafeEmbed(title="Possible Alt Account Joined", description="")
            embed.add_field(
                name="Person", value=f"{member.mention} ({member.id})", inline=False
            )
            embed.add_field(
                name="Chance",
                value=f"There is a **{(chance * 100):.0f}%** chance that {member} is an alt.",
                inline=False,
            )
            if details:
                embed.add_field(name="Factors", value=details, inline=False)

            await self.bot.get_democraciv_channel(
                mk.DemocracivChannel.MODERATION_NOTIFICATIONS_CHANNEL
            ).send(embed=embed)

    @commands.command(name="report")
    @commands.dm_only()
    async def report(self, ctx: context.CustomContext):
        """Report something to the {democraciv} Moderation

        This command only works in DMs with me."""

        is_anon = await ctx.confirm(
            "You can report something directly to the mods with this command. Abuse "
            f"(i.e. spamming joke reports) will be punished.\n\n\n{config.USER_INTERACTION_REQUIRED} "
            "Do you want this report to be anonymous?"
        )

        content = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the details of your report. This will abort after"
            " 10 minutes of no reply.",
            timeout=600,
        )

        if len(content) > 2048:
            return await ctx.send(
                f"{config.NO} Text cannot be more than 2048 characters."
            )

        pretty_anon = "be anonymous" if is_anon else "not be anonymous"
        reaction = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to send this report? "
            f"The report will **{pretty_anon}**."
        )

        if not reaction:
            return await ctx.send("Cancelled.")

        embed = text.SafeEmbed(title=":exclamation: New Report", description=content)

        if is_anon:
            from_value = "*Anonymous Report*"
        else:
            from_value = str(ctx.author)

        embed.add_field(name="From", value=from_value)

        await self.bot.get_democraciv_channel(
            mk.DemocracivChannel.MODERATION_NOTIFICATIONS_CHANNEL
        ).send(
            content=self.bot.get_democraciv_role(mk.DemocracivRole.MODERATION).mention,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(roles=True),
        )

        await ctx.send(f"{config.YES} Report was sent.")

    async def safe_send_mod_links(self, ctx, embed):
        if isinstance(ctx.channel, discord.Thread) or len(ctx.channel.members) >= 20:
            await ctx.message.add_reaction("\U0001f4e9")
            return await ctx.author.send(embed=embed)

        unsafe_members = [
            member
            for member in ctx.channel.members
            if not member.bot and not member.guild_permissions.administrator
        ]

        if unsafe_members:
            await ctx.message.add_reaction("\U0001f4e9")
            await ctx.author.send(embed=embed)
        else:
            await ctx.send(embed=embed)

    @commands.command(name="say")
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def say(self, ctx, *, content: str):
        """Make the bot say something"""
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            raise exceptions.ForbiddenError(
                exceptions.ForbiddenTask.MESSAGE_DELETE, content
            )

        await ctx.send(content)

    @commands.command(name="alt", hidden=True)
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def alt(self, ctx, *, person: Fuzzy[CaseInsensitiveMember]):
        """Check if someone is an alt"""
        chance, details = await self.calculate_alt_chance(person)

        embed = text.SafeEmbed(
            title="Possible Alt Detection",
            description="This is in no way perfect and should always be taken with a grain of salt.",
        )
        embed.add_field(
            name="Target", value=f"{person.mention} ({person.id})", inline=False
        )
        embed.add_field(
            name="Result",
            value=f"There is a **{(chance * 100):.0f}%** chance that {person} is an alt.",
        )

        if details:
            embed.add_field(name="Factors", value=details, inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="hub", aliases=["modhub", "moderationhub", "mhub"])
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def hub(self, ctx):
        """Link to the Moderation Hub"""
        link = token.MOD_HUB or "https://hastebin.com/afijavahox.coffeescript"
        embed = text.SafeEmbed(title="Moderation Hub", url=link)
        await self.safe_send_mod_links(ctx, embed)

    @commands.command(name="registry")
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def registry(self, ctx):
        """Link to the Democraciv Registry"""
        link = token.REGISTRY or "https://hastebin.com/afijavahox.coffeescript"
        embed = text.SafeEmbed(title="Democraciv Registry", url=link)
        await self.safe_send_mod_links(ctx, embed)

    @commands.command(name="drive", aliases=["googledrive", "gdrive"])
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def gdrive(self, ctx):
        """Link to the Moderation Google Drive"""
        link = token.MOD_DRIVE or "https://hastebin.com/afijavahox.coffeescript"
        embed = text.SafeEmbed(title="Moderation Google Drive", url=link)
        await self.safe_send_mod_links(ctx, embed)

    @commands.command(name="pin", aliases=["pins", "electiontool", "pintool"])
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def electiontool(self, ctx):
        """Link to DerJonas' Election Tool"""
        link = token.PIN_TOOL or "https://hastebin.com/afijavahox.coffeescript"
        embed = text.SafeEmbed(title="DerJonas' Election Tool", url=link)
        await self.safe_send_mod_links(ctx, embed)

    @commands.command(
        name="modguidelines",
        aliases=["modguideline", "mod", "mods", "modprocedure", "modprocedures"],
    )
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def modguidelines(self, ctx):
        """Link to DerJonas' Democraciv Moderation Guidelines"""
        link = token.MOD_GUIDELINES or "https://hastebin.com/afijavahox.coffeescript"
        embed = text.SafeEmbed(
            title="DerJonas' Democraciv Moderation Guidelines & Procedures", url=link
        )
        await self.safe_send_mod_links(ctx, embed)

    @commands.command(name="quire", aliases=["q"])
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def quire(self, ctx):
        """Quire Project Management"""
        embed = text.SafeEmbed(
            title="Quire", url="https://quire.io/c/democraciv-moderation"
        )
        await ctx.send(embed=embed)

    @commands.command(name="kick")
    @commands.guild_only()
    @commands.bot_has_permissions(kick_members=True)
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, *, person: Fuzzy[CaseInsensitiveMember]):
        """Kick someone"""
        if person == ctx.author:
            return await ctx.send(f"{config.NO} You can't kick yourself.")

        if person == self.bot.owner:
            #  :)
            raise exceptions.ForbiddenError(exceptions.ForbiddenTask.MEMBER_KICK)

        if person == ctx.guild.me:
            return await ctx.send(f"{config.NO} I can't kick myself.")

        if person.top_role >= ctx.author.top_role:
            return await ctx.send(
                f"{config.NO} You aren't allowed to kick someone with a higher role than yours."
            )

        formatted_reason = f"Action requested by {ctx.author} ({ctx.author.id})."

        await self.bot.safe_send_dm(
            target=person,
            reason="ban_kick_mute",
            message=f":boot: You were **kicked** from {ctx.guild.name}.",
        )

        try:
            await ctx.guild.kick(person, reason=formatted_reason)
        except discord.Forbidden:
            raise exceptions.ForbiddenError(exceptions.ForbiddenTask.MEMBER_KICK)

        await ctx.send(f"{config.YES} {person} was kicked.")

    @commands.command(name="clear")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_messages=True)
    async def clear(
        self,
        ctx,
        amount: int,
        *,
        target: Fuzzy[
            CaseInsensitiveMember, CaseInsensitiveUser, FuzzySettings(weights=(5, 1))
        ] = None,
    ):
        """Purge an amount of messages in the current channel"""
        if amount > 500 or amount < 0:
            return await ctx.send(
                f"{config.NO} You can only clear up to 500 messages at most."
            )

        def check(message):
            if target:
                return message.author.id == target.id
            return True

        try:
            deleted = await ctx.channel.purge(limit=amount, check=check)
        except discord.Forbidden:
            raise exceptions.ForbiddenError(task=ForbiddenTask.MESSAGE_DELETE)

        await ctx.send(
            f"{config.YES} Deleted **{len(deleted)}** messages.", delete_after=5
        )

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        muted_role = discord.utils.get(guild.roles, name="Muted")

        if muted_role is None:
            try:
                muted_role = await guild.create_role(name="Muted")
            except discord.Forbidden:
                return

        if guild.id != self.bot.dciv.id:
            for channel in guild.text_channels:
                self.bot.loop.create_task(
                    channel.set_permissions(
                        muted_role, send_messages=False, add_reactions=False
                    )
                )

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        muted_role = discord.utils.get(channel.guild.roles, name="Muted")

        if muted_role is None:
            try:
                muted_role = await channel.guild.create_role(name="Muted")
            except discord.Forbidden:
                raise exceptions.ForbiddenError(
                    exceptions.ForbiddenTask.CREATE_ROLE, detail="Muted"
                )

        await channel.set_permissions(
            muted_role, send_messages=False, add_reactions=False
        )

    @commands.command(name="mute")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    async def mute(self, ctx, *, person: Fuzzy[CaseInsensitiveMember]):
        """Mute someone"""

        muted_role = discord.utils.get(ctx.guild.roles, name="Muted")

        if muted_role is None:
            try:
                muted_role = await ctx.guild.create_role(name="Muted")
                for channel in ctx.guild.text_channels:
                    self.bot.loop.create_task(
                        channel.set_permissions(
                            muted_role, send_messages=False, add_reactions=False
                        )
                    )
            except discord.Forbidden:
                raise exceptions.ForbiddenError(
                    exceptions.ForbiddenTask.CREATE_ROLE, detail="Muted"
                )

        if muted_role is None:
            raise exceptions.RoleNotFoundError("Muted")

        if muted_role in person.roles:
            return await ctx.send(f"{config.NO} {person} is already muted.")

        formatted_reason = f"Action requested by {ctx.author} ({ctx.author.id})"

        if person == ctx.author:
            return await ctx.send(f"{config.NO} You can't mute yourself.")

        if person == ctx.guild.me:
            return await ctx.send(f"{config.NO} You can't mute me.")

        try:
            await person.add_roles(muted_role, reason=formatted_reason)
        except discord.Forbidden:
            raise exceptions.ForbiddenError(
                exceptions.ForbiddenTask.ADD_ROLE, detail="Muted"
            )

        await self.bot.safe_send_dm(
            target=person,
            reason="ban_kick_mute",
            message=f":zipper_mouth: You were **muted** in {ctx.guild.name}.",
        )

        await ctx.send(f"{config.YES} {person} was muted.")

    @commands.command(name="unmute")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    async def unmute(self, ctx, *, person: Fuzzy[CaseInsensitiveMember]):
        """Unmute someone"""

        muted_role = discord.utils.get(ctx.guild.roles, name="Muted")

        if muted_role is None:
            raise exceptions.RoleNotFoundError("Muted")

        if muted_role not in person.roles:
            return await ctx.send(f"{config.NO} {person} is not muted.")

        try:
            await person.remove_roles(
                muted_role, reason=f"Action requested by {ctx.author}."
            )
        except discord.Forbidden:
            raise exceptions.ForbiddenError(
                exceptions.ForbiddenTask.REMOVE_ROLE, detail="Muted"
            )

        await self.bot.safe_send_dm(
            target=person,
            reason="ban_kick_mute",
            message=f":innocent: You were **unmuted** in {ctx.guild.name}.",
        )

        await ctx.send(f"{config.YES} {person} was unmuted.")

    @commands.command(name="ban")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx, *, person: BanConverter):
        """Ban someone

        If you want to ban a user that is not in this server, use the user's ID instead.

        **Example**
            `{PREFIX}{COMMAND} @Das` ban by mention
            `{PREFIX}{COMMAND} Queen Das` ban by nickname
            `{PREFIX}{COMMAND} darthspectrum` ban by username
            `{PREFIX}{COMMAND} darthspectrum#4924` ban by username#discriminator
            `{PREFIX}{COMMAND} 561280863464062977` ban by ID"""

        if isinstance(person, (discord.Member, discord.User)):
            member_object = person
            member_id = person.id
        elif isinstance(person, int):
            member_object = None
            member_id = person
        else:
            return await ctx.send(f"{config.NO} I couldn't find that person.")

        if member_id is None:
            return await ctx.send(f"{config.NO} I couldn't find that person.")

        if member_id == ctx.author.id:
            return await ctx.send(f"{config.NO} You can't ban yourself.")

        if member_id == self.bot.owner.id:
            #  :)
            raise exceptions.ForbiddenError(exceptions.ForbiddenTask.MEMBER_BAN)

        if member_id == ctx.guild.me.id:
            return await ctx.send(f"{config.NO} I can't ban myself.")

        if (
            member_object
            and isinstance(member_object, discord.Member)
            and member_object.top_role >= ctx.author.top_role
        ):
            return await ctx.send(
                f"{config.NO} You aren't allowed to ban someone with a higher role than yours."
            )

        formatted_reason = f"Action requested by {ctx.author} ({ctx.author.id})."

        if member_object:
            await self.bot.safe_send_dm(
                target=member_object,
                reason="ban_kick_mute",
                message=f":no_entry: You were **banned** from {ctx.guild.name}.",
            )

        try:
            await ctx.guild.ban(
                discord.Object(id=member_id),
                reason=formatted_reason,
                delete_message_days=0,
            )
        except discord.Forbidden:
            raise exceptions.ForbiddenError(exceptions.ForbiddenTask.MEMBER_BAN)
        except discord.HTTPException:
            return await ctx.send(f"{config.NO} I couldn't find that person.")

        if member_object:
            name = str(member_object)
        else:
            name = f"The Discord user with ID `{member_id}`"

        await ctx.send(f"{config.YES} {name} was banned.")

    @commands.command(name="unban")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx, *, person: UnbanConverter):
        """Unban someone

        **Example**
            `{PREFIX}{COMMAND} darthspectrum` unban by Discord username
            `{PREFIX}{COMMAND} 561280863464062977` unban by Discord ID"""

        user_object = person
        user_id = person.id

        if user_id is None:
            return await ctx.send(f"{config.NO} I couldn't find that person.")

        formatted_reason = f"Action requested by {ctx.author} ({ctx.author.id})."

        try:
            await ctx.guild.unban(discord.Object(id=user_id), reason=formatted_reason)
        except discord.Forbidden:
            raise exceptions.ForbiddenError(exceptions.ForbiddenTask.MEMBER_BAN)
        except discord.HTTPException:
            return await ctx.send(f"{config.NO} That person is not banned.")

        if user_object:
            name = str(user_object)
        else:
            name = f"The Discord user with ID `{user_id}`"

        await ctx.send(f"{config.YES} {name} was unbanned.")

    @commands.command(name="archivechannel")
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def archivechannel(self, ctx, *, channel: Fuzzy[CaseInsensitiveTextChannel]):
        """Archive a channel and automatically set the right permissions

        **Example**
            `{PREFIX}{COMMAND} #public-form`
            `{PREFIX}{COMMAND} legislature`"""

        archive_category = await ctx.converted_input(
            f"{config.USER_INTERACTION_REQUIRED} What archive category should "
            f"I use for this?",
            converter=converter.CaseInsensitiveCategoryChannel,
            return_input_on_fail=False,
        )

        everyone_perms = discord.PermissionOverwrite(
            read_message_history=False,
            send_messages=False,
            read_messages=False,
            add_reactions=False,
        )
        everyone_role = self.bot.dciv.default_role

        archive_perms = discord.PermissionOverwrite(
            read_message_history=True,
            send_messages=False,
            read_messages=True,
            add_reactions=False,
        )
        archives_role = discord.utils.get(self.bot.dciv.roles, name="Archives")

        if archives_role is None:
            return await ctx.send(
                f"{config.NO} There is no role named `Archives` for me to use."
            )

        await channel.edit(
            name=f"mk{self.bot.mk.MARK}-{channel.name}"
            if not channel.name.startswith(f"mk{self.bot.mk.MARK}-")
            else channel.name,
            overwrites={everyone_role: everyone_perms, archives_role: archive_perms},
            category=archive_category,
        )

        await self.bot.db.execute(
            "DELETE FROM guild_private_channel WHERE guild_id = $1 AND channel_id = $2",
            channel.guild.id,
            channel.id,
        )

        await ctx.send(f"{config.YES} Channel was archived.")

    @commands.command(name="archivecategory")
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def archivecategory(
        self,
        ctx: context.CustomContext,
        *,
        category: Fuzzy[CaseInsensitiveCategoryChannel],
    ):
        """Move all channels in a category into the Archives and set the right permissions"""

        archive_category = await ctx.converted_input(
            f"{config.USER_INTERACTION_REQUIRED} What archive category should "
            f"I use for this?",
            converter=converter.CaseInsensitiveCategoryChannel,
            return_input_on_fail=False,
        )

        reaction = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want archive every channel in `{category}`?"
        )

        if not reaction:
            return await ctx.send("Cancelled.")

        async with ctx.typing():
            everyone_perms = discord.PermissionOverwrite(
                read_message_history=False,
                send_messages=False,
                read_messages=False,
                add_reactions=False,
            )
            everyone_role = self.bot.dciv.default_role
            archive_perms = discord.PermissionOverwrite(
                read_message_history=True,
                send_messages=False,
                read_messages=True,
                add_reactions=False,
            )
            archives_role = discord.utils.get(self.bot.dciv.roles, name="Archives")

            if archives_role is None:
                return await ctx.send(
                    f"{config.NO} There is no role named `Archives` for me to use."
                )

            for channel in category.text_channels:
                await channel.send(
                    f":tada: Thanks for playing Democraciv MK{self.bot.mk.MARK}!"
                )
                await channel.edit(
                    name=f"mk{self.bot.mk.MARK}-{channel.name}"
                    if not channel.name.startswith(f"mk{self.bot.mk.MARK}-")
                    else channel.name,
                    overwrites={
                        everyone_role: everyone_perms,
                        archives_role: archive_perms,
                    },
                    category=archive_category,
                )

                await self.bot.db.execute(
                    "DELETE FROM guild_private_channel WHERE guild_id = $1 AND channel_id = $2",
                    channel.guild.id,
                    channel.id,
                )

        await ctx.send(f"{config.YES} Done.")


def setup(bot):
    bot.add_cog(Moderation(bot))
