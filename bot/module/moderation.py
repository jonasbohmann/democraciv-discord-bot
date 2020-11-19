import typing
import discord
import datetime

from bot import DemocracivBot
from discord.ext import commands
from bot.utils import exceptions, text, context, checks
from bot.config import token, config, mk
from bot.utils.exceptions import ForbiddenTask
from bot.utils.converter import UnbanConverter, BanConverter, CaseInsensitiveMember


class Moderation(context.CustomCog):
    """Commands for the Mod Team of this server."""

    async def calculate_alt_chance(self, member: discord.Member) -> (int, str):
        is_alt_chance = 0
        factor_details = ""

        default_avatars = ["https://cdn.discordapp.com/embed/avatars/0.png",
                           "https://cdn.discordapp.com/embed/avatars/1.png",
                           "https://cdn.discordapp.com/embed/avatars/2.png",
                           "https://cdn.discordapp.com/embed/avatars/3.png",
                           "https://cdn.discordapp.com/embed/avatars/4.png"]

        if member.bot:
            return 0, "Bot Account (0%)"

        # Check how long it has been since the user registered
        discord_registration_duration_in_s = (datetime.datetime.utcnow() - member.created_at).total_seconds()
        hours_since = divmod(discord_registration_duration_in_s, 3600)[0]

        if hours_since <= 48:
            # If the account is new, check if the they bothered to change the default avatar
            is_alt_chance += 0.1
            factor_details += "Less than 48 hours since registration (+10%)\n"
            if str(member.avatar_url_as(static_format="png")) in default_avatars:
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

        weird_names = ["alt", "mysterious", "anonymous", "anon", "banned", "ban", "das", "mysterybox", "not",
                       "definitelynot", "darthspectrum"]

        if any(name in member.name.lower() for name in weird_names) or any(
                name in member.display_name.lower() for name in weird_names):
            # Check if user has any names that are associated with alt accounts in the past
            is_alt_chance += 0.45
            factor_details += "Suspicious username (+45%)\n"

        if member.status != discord.Status.offline:
            # If the user didn't download a Discord App, but is accessing Discord through their browser, chances
            # increase that they're an alt
            if isinstance(member.web_status, discord.Status) and member.web_status != discord.Status.offline:
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
            mod_role = mk.get_democraciv_role(self.bot, mk.DemocracivRole.MODERATION)
        except exceptions.RoleNotFoundError:
            return

        if mod_role is None:
            return

        if mod_role in message.role_mentions:
            embed = self.bot.embeds.embed_builder(title=f":pushpin:  New Request in #{message.channel.name}",
                                                  description=message.content)
            embed.add_field(name="From", value=message.author.mention)
            embed.add_field(name="Original", value=f"[Jump!]({message.jump_url})")
            await mk.get_democraciv_channel(self.bot,
                                            mk.DemocracivChannel.MODERATION_NOTIFICATIONS_CHANNEL).send(embed=embed)

    @commands.Cog.listener(name="on_member_join")
    async def possible_alt_listener(self, member):
        if member.guild != self.bot.dciv:
            return

        if member.bot:
            return

        chance, details = await self.calculate_alt_chance(member)

        if chance >= 0.2:
            embed = self.bot.embeds.embed_builder(title="Possible Alt Account Joined", description="")
            embed.add_field(name="Member", value=f"{member.mention} ({member.id})", inline=False)
            embed.add_field(name="Chance",
                            value=f"There is a **{(chance * 100):.0f}%** chance that {member} is an alt.",
                            inline=False)
            if details:
                embed.add_field(name="Factors", value=details, inline=False)

            await mk.get_democraciv_channel(self.bot,
                                            mk.DemocracivChannel.MODERATION_NOTIFICATIONS_CHANNEL).send(embed=embed)

    @commands.command(name='report')
    @commands.dm_only()
    async def report(self, ctx):
        """Report something to the Democraciv Moderation

         This command only works in DMs with me."""

        flow = Flow(self.bot, ctx)

        anon_question = await ctx.send("You can report something directly to the mods with this command. Abuse "
                                       "(i.e. spamming joke reports) will be punished.\n\n\n:information_source: "
                                       "Do you want this report to be anonymous?")

        is_anon = True

        reaction = await flow.get_yes_no_reaction_confirm(anon_question, 150)

        if reaction is None:
            return

        if reaction:
            is_anon = True

        elif not reaction:
            is_anon = False

        await ctx.send(":information_source: Reply with the details of your report. This will abort after"
                       " 10 minutes of no reply.")

        content = await flow.get_text_input(600)

        if not content:
            return

        if len(content) > 2048:
            return await ctx.send(":x: Text cannot be more than 2048 characters.")

        pretty_anon = "be anonymous" if is_anon else "not be anonymous"

        are_you_sure = await ctx.send(f":information_source: Are you sure that you want to send this report? "
                                      f"The report will **{pretty_anon}**.")

        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 150)

        if reaction is None:
            return

        if reaction:
            embed = self.bot.embeds.embed_builder(title=":exclamation: New Report", description=content)

            if is_anon:
                from_value = "*Anonymous Report*"
            else:
                from_value = str(ctx.author)

            embed.add_field(name="From", value=from_value)

            await mk.get_democraciv_channel(self.bot,
                                            mk.DemocracivChannel.MODERATION_NOTIFICATIONS_CHANNEL).send(
                content=mk.get_democraciv_role(self.bot, mk.DemocracivRole.MODERATION).mention, embed=embed)

            await ctx.send(":white_check_mark: Report was sent.")

        elif not reaction:
            return await ctx.send("Aborted.")

    async def safe_send_mod_links(self, ctx, embed):
        if len(ctx.channel.members) >= 20:
            await ctx.message.add_reaction("\U0001f4e9")
            return await ctx.author.send(embed=embed)

        unsafe_members = [member for member in ctx.channel.members if not member.bot
                          and mk.get_democraciv_role(self.bot, mk.DemocracivRole.MODERATION) not in member.roles]

        if unsafe_members:
            await ctx.message.add_reaction("\U0001f4e9")
            await ctx.author.send(embed=embed)
        else:
            await ctx.send(embed=embed)

    @commands.command(name='restart', aliases=['stop'])
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def restart(self, ctx):
        """Restarts the bot"""
        await ctx.send(':wave: Restarting...')
        await self.bot.close()

    @commands.command(name='say')
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def say(self, ctx, *, content: str):
        """Make the bot say something"""
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            raise exceptions.ForbiddenError(exceptions.ForbiddenTask.MESSAGE_DELETE, content)

        await ctx.send(content)

    @commands.command(name='alt')
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def alt(self, ctx, member: typing.Union[discord.Member, CaseInsensitiveMember]):
        """Check if someone is an alt"""
        chance, details = await self.calculate_alt_chance(member)

        embed = self.bot.embeds.embed_builder(title="Possible Alt Detection", description="This is in no way perfect "
                                                                                          "and should always be taken"
                                                                                          " with a grain of salt.")
        embed.add_field(name="Target", value=f"{member.mention} ({member.id})", inline=False)
        embed.add_field(name="Result", value=f"There is a **{(chance * 100):.0f}%** chance that {member} is an alt.")

        if details:
            embed.add_field(name="Factors", value=details, inline=False)

        await ctx.send(embed=embed)

    @commands.command(name='hub', aliases=['modhub', 'moderationhub', 'mhub'])
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def hub(self, ctx):
        """Link to the Moderation Hub"""
        link = token.MOD_HUB or 'https://hastebin.com/afijavahox.coffeescript'
        embed = self.bot.embeds.embed_builder(title="Moderation Hub", description=f"[Link]({link})",
                                              has_footer=False)
        await self.safe_send_mod_links(ctx, embed)

    @commands.command(name='registry')
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def registry(self, ctx):
        """Link to the Democraciv Registry"""
        link = token.REGISTRY or 'https://hastebin.com/afijavahox.coffeescript'
        embed = self.bot.embeds.embed_builder(title="Democraciv Registry", description=f"[Link]({link})",
                                              has_footer=False)
        await self.safe_send_mod_links(ctx, embed)

    @commands.command(name='drive', aliases=['googledrive', 'gdrive'])
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def gdrive(self, ctx):
        """Link to the Google Drive for MK6"""
        link = token.MK6_DRIVE or 'https://hastebin.com/afijavahox.coffeescript'
        embed = self.bot.embeds.embed_builder(title="Google Drive for MK6", description=f"[Link]({link})",
                                              has_footer=False)
        await self.safe_send_mod_links(ctx, embed)

    @commands.command(name='pin', aliases=['pins', 'electiontool', 'pintool'])
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def electiontool(self, ctx):
        """Link to DerJonas' Election Tool"""
        link = token.PIN_TOOL or 'https://hastebin.com/afijavahox.coffeescript'
        embed = self.bot.embeds.embed_builder(title="DerJonas' Election Tool", description=f"[Link]({link})",
                                              has_footer=False)
        await self.safe_send_mod_links(ctx, embed)

    @commands.command(name='modguidelines', aliases=['modguideline', 'mod', 'mods', 'modprocedure', 'modprocedures'])
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def modguidelines(self, ctx):
        """Link to the Democraciv Moderation Guidelines"""
        link = token.MOD_GUIDELINES or 'https://hastebin.com/afijavahox.coffeescript'
        embed = self.bot.embeds.embed_builder(title="Democraciv Moderation Guidelines & Procedures",
                                              description=f"[Link]({link})",
                                              has_footer=False)
        await self.safe_send_mod_links(ctx, embed)

    @commands.command(name='quire', aliases=['q'])
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def quire(self, ctx):
        """Quire Project Management"""
        embed = self.bot.embeds.embed_builder(title='Quire', description="https://quire.io/c/democraciv-moderation")
        await ctx.send(embed=embed)

    @commands.command(name='kick')
    @commands.guild_only()
    @commands.bot_has_permissions(kick_members=True)
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: typing.Union[discord.Member, CaseInsensitiveMember], *, reason: str = None):
        """Kick someone"""
        if member == ctx.author:
            return await ctx.send(":x: You can't kick yourself.")

        if member == self.bot.owner:
            #  :)
            raise exceptions.ForbiddenError(exceptions.ForbiddenTask.MEMBER_KICK)

        if member == ctx.guild.me:
            return await ctx.send(":x: I can't kick myself.")

        if member.top_role >= ctx.author.top_role:
            return await ctx.send(":x: You aren't allowed to kick someone with a higher role than yours.")

        if reason:
            if len(reason) > 400:
                return await ctx.send(":x: The reason cannot be longer than 400 characters.")

            formatted_reason = f"Action requested by {ctx.author} ({ctx.author.id}) with reason: {reason}"
        else:
            formatted_reason = f"Action requested by {ctx.author} ({ctx.author.id}) with no specified reason."

        await self.bot.safe_send_dm(target=member, reason="ban_kick_mute",
                                    message=f":boot: You were **kicked** from {ctx.guild.name}.")

        try:
            await ctx.guild.kick(member, reason=formatted_reason)
        except discord.Forbidden:
            raise exceptions.ForbiddenError(exceptions.ForbiddenTask.MEMBER_KICK)

        await ctx.send(f":white_check_mark: {member} was kicked.")

    @kick.error
    async def kickerror(self, ctx, error):
        if isinstance(error, commands.BadUnionArgument):
            await ctx.send(":x: I couldn't find that person.")

    @commands.command(name="clear")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int, target: typing.Union[discord.Member, CaseInsensitiveMember] = None):
        """Purge an amount of messages in the current channel"""
        if amount > 500 or amount < 0:
            return await ctx.send(":x: Invalid amount! The maximum is 500.")

        def check(message):
            if target:
                return message.author.id == target.id
            return True

        try:
            deleted = await ctx.channel.purge(limit=amount, check=check)
        except discord.Forbidden:
            raise exceptions.ForbiddenError(task=ForbiddenTask.MESSAGE_DELETE)

        await ctx.send(f':white_check_mark: Deleted **{len(deleted)}** messages.', delete_after=5)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        muted_role = discord.utils.get(guild.roles, name="Muted")

        if muted_role is None:
            try:
                muted_role = await guild.create_role(name="Muted")
                for channel in guild.text_channels:
                    try:
                        await channel.set_permissions(muted_role, send_messages=False)
                    except discord.HTTPException:
                        continue
            except discord.Forbidden:
                raise exceptions.ForbiddenError(exceptions.ForbiddenTask.CREATE_ROLE, detail="Muted")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        muted_role = discord.utils.get(channel.guild.roles, name="Muted")

        if muted_role is None:
            try:
                muted_role = await channel.guild.create_role(name="Muted")
            except discord.Forbidden:
                raise exceptions.ForbiddenError(exceptions.ForbiddenTask.CREATE_ROLE, detail="Muted")

        await channel.set_permissions(muted_role, send_messages=False)

    @commands.command(name='mute')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    async def mute(self, ctx, member: typing.Union[discord.Member, CaseInsensitiveMember], *, reason: str = None):
        """Mute someone"""

        muted_role = discord.utils.get(ctx.guild.roles, name="Muted")

        if muted_role is None:
            try:
                muted_role = await ctx.guild.create_role(name="Muted")
                for channel in ctx.guild.text_channels:
                    await channel.set_permissions(muted_role, send_messages=False)
            except discord.Forbidden:
                raise exceptions.ForbiddenError(exceptions.ForbiddenTask.CREATE_ROLE, detail="Muted")

        if muted_role is None:
            raise exceptions.RoleNotFoundError("Muted")

        if muted_role in member.roles:
            return await ctx.send(f":x: {member} is already muted.")

        if reason:
            if len(reason) > 400:
                return await ctx.send(":x: The reason cannot be longer than 400 characters.")

            formatted_reason = f"Action requested by {ctx.author} ({ctx.author.id}) with reason: {reason}"
        else:
            formatted_reason = f"Action requested by {ctx.author} ({ctx.author.id}) with no specified reason."

        if member == ctx.author:
            return await ctx.send(":x: You can't mute yourself.")

        if member == ctx.guild.me:
            return await ctx.send(":x: You can't mute me.")

        try:
            await member.add_roles(muted_role, reason=formatted_reason)
        except discord.Forbidden:
            raise exceptions.ForbiddenError(exceptions.ForbiddenTask.ADD_ROLE, detail="Muted")

        await self.bot.safe_send_dm(target=member, reason="ban_kick_mute",
                                    message=f":zipper_mouth: You were **muted** in {ctx.guild.name}.")

        await ctx.send(f":white_check_mark: {member} was muted.")

    @mute.error
    async def muteerror(self, ctx, error):
        if isinstance(error, commands.BadUnionArgument):
            await ctx.send(":x: I couldn't find that person.")

    @commands.command(name='unmute')
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    async def unmute(self, ctx, member: typing.Union[discord.Member, CaseInsensitiveMember]):
        """Unmute someone"""

        muted_role = discord.utils.get(ctx.guild.roles, name="Muted")

        if muted_role is None:
            raise exceptions.RoleNotFoundError("Muted")

        if muted_role not in member.roles:
            return await ctx.send(f":x: {member} is not muted.")

        try:
            await member.remove_roles(muted_role, reason=f"Action requested by {ctx.author}.")
        except discord.Forbidden:
            raise exceptions.ForbiddenError(exceptions.ForbiddenTask.REMOVE_ROLE, detail="Muted")

        await self.bot.safe_send_dm(target=member, reason="ban_kick_mute",
                                    message=f":innocent: You were **unmuted** in {ctx.guild.name}.")

        await ctx.send(f":white_check_mark: {member} was unmuted.")

    @unmute.error
    async def unmuteerror(self, ctx, error):
        if isinstance(error, commands.BadUnionArgument):
            await ctx.send(":x: I couldn't find that person.")

    @commands.command(name='ban')
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx, member: BanConverter, *, reason: str = None):
        """Ban someone

        If you want to ban a user that is not in this server, use the user's ID instead.

        **Example:**
            `-ban @Das` ban by mention
            `-ban Queen Das` ban by nickname
            `-ban darthspectrum` ban by username
            `-ban darthspectrum#4924` ban by username#discriminator
            `-ban 561280863464062977` ban by ID"""

        if isinstance(member, discord.Member):
            member_object = member
            member_id = member.id
        elif isinstance(member, int):
            member_object = None
            member_id = member
        else:
            return await ctx.send(":x: I couldn't find that person.")

        if member_id is None:
            return await ctx.send(":x: I couldn't find that person.")

        if member_object == ctx.author:
            return await ctx.send(":x: You can't ban yourself.")

        if member_object == self.bot.owner:
            #  :)
            raise exceptions.ForbiddenError(exceptions.ForbiddenTask.MEMBER_BAN)

        if member_object == ctx.guild.me:
            return await ctx.send(":x: I can't ban myself.")

        if member_object is not None and member_object.top_role >= ctx.author.top_role:
            return await ctx.send(":x: You aren't allowed to ban someone with a higher role than yours.")

        if reason:
            if len(reason) > 400:
                return await ctx.send(":x: The reason cannot be longer than 400 characters.")

            formatted_reason = f"Action requested by {ctx.author} ({ctx.author.id}) with reason: {reason}"
        else:
            formatted_reason = f"Action requested by {ctx.author} ({ctx.author.id}) with no specified reason."

        if member_object:
            await self.bot.safe_send_dm(target=member_object, reason="ban_kick_mute",
                                        message=f":no_entry: You were **banned** from {ctx.guild.name}.")

        try:
            await ctx.guild.ban(discord.Object(id=member_id), reason=formatted_reason, delete_message_days=0)
        except discord.Forbidden:
            raise exceptions.ForbiddenError(exceptions.ForbiddenTask.MEMBER_BAN)
        except discord.HTTPException:
            return await ctx.send(":x: I couldn't find that person.")

        if member_object:
            name = str(member_object)
        else:
            name = f"The Discord user with ID `{member_id}`"

        await ctx.send(f":white_check_mark: {name} was banned.")

    @ban.error
    async def banerror(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(":x: I couldn't find that person.")

    @commands.command(name='unban')
    @commands.guild_only()
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx, user: UnbanConverter, *, reason: str = None):
        """Unban someone

        **Example:**
            `-unban darthspectrum` unban by Discord username
            `-unban 561280863464062977` unban by Discord ID"""

        user_object = user
        user_id = user.id

        if user_id is None:
            return await ctx.send(":x: I couldn't find that person.")

        if reason:
            if len(reason) > 400:
                return await ctx.send(":x: The reason cannot be longer than 400 characters.")

            formatted_reason = f"Action requested by {ctx.author} ({ctx.author.id}) with reason: {reason}"
        else:
            formatted_reason = f"Action requested by {ctx.author} ({ctx.author.id}) with no specified reason."

        try:
            await ctx.guild.unban(discord.Object(id=user_id), reason=formatted_reason)
        except discord.Forbidden:
            raise exceptions.ForbiddenError(exceptions.ForbiddenTask.MEMBER_BAN)
        except discord.HTTPException:
            return await ctx.send(":x: That person is not banned.")

        if user_object:
            name = str(user_object)
        else:
            name = f"The Discord user with ID `{user_id}`"

        await ctx.send(f":white_check_mark: {name} was unbanned.")

    @unban.error
    async def unbanerror(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(":x: I couldn't find that person.")

    @commands.command(name='archivechannel')
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def archivechannel(self, ctx, *, channel: discord.TextChannel):
        """Archive a channel and automatically set the right permissions

        **Examples:**
            `-archivechannel #public-form`
            `-archivechannel legislature` """

        everyone_perms = discord.PermissionOverwrite(read_message_history=False, send_messages=False,
                                                     read_messages=False)
        everyone_role = self.bot.dciv.default_role

        archive_perms = discord.PermissionOverwrite(read_message_history=True, send_messages=False,
                                                    read_messages=True)
        archives_role = discord.utils.get(self.bot.dciv.roles, name="Archives")

        def predicate(c):
            return c.name.lower() == f"mk{self.bot.mk.MARK}-archive"

        archive_category = discord.utils.find(predicate, self.bot.dciv.categories)

        if archives_role is None:
            return await ctx.send(":x: There is no role named `Archives` for me to use.")

        if archive_category is None:
            return await ctx.send(f":x: There is no category named `MK{self.bot.mk.MARK}-Archive` for me to use.")

        await channel.edit(name=f"mk{self.bot.mk.MARK}-{channel.name}",
                           overwrites={everyone_role: everyone_perms, archives_role: archive_perms},
                           category=archive_category)

        await ctx.send(":white_check_mark: Channel was archived.")

    @commands.command(name='archiveoldgov')
    @checks.has_democraciv_role(mk.DemocracivRole.MODERATION)
    async def archiveoldgov(self, ctx):
        """Move all channels in the Government category and #propaganda into the Archives and set the right permissions
        """

        flow = Flow(self.bot, ctx)

        are_you_sure = await ctx.send(
            f":information_source: Are you sure that you want archive every government channel?")

        reaction = await flow.get_yes_no_reaction_confirm(are_you_sure, 200)

        if reaction is None:
            return

        if not reaction:
            return await ctx.send("Aborted.")

        elif reaction:
            async with ctx.typing():
                government_category: discord.CategoryChannel = discord.utils.get(
                    self.bot.dciv.categories,
                    name="Government")

                if government_category is None:
                    return await ctx.send(":x: There is no category named `Government` for me to archive.")

                def predicate(c):
                    return c.name.lower() == f"mk{self.bot.mk.MARK}-archive"

                archive_category = discord.utils.find(predicate, self.bot.dciv.categories)

                if archive_category is None:
                    return await ctx.send(
                        f":x: There is no category named `MK{self.bot.mk.MARK}-Archive` for me to use.")

                everyone_perms = discord.PermissionOverwrite(read_message_history=False, send_messages=False,
                                                             read_messages=False)
                everyone_role = self.bot.dciv.default_role
                archive_perms = discord.PermissionOverwrite(read_message_history=True, send_messages=False,
                                                            read_messages=True)
                archives_role = discord.utils.get(self.bot.dciv.roles, name="Archives")

                if archives_role is None:
                    return await ctx.send(":x: There is no role named `Archives` for me to use.")

                for channel in government_category.text_channels:
                    await channel.send(f":tada: Thanks for playing Democraciv MK{self.bot.mk.MARK}!")
                    await channel.edit(name=f"mk{self.bot.mk.MARK}-{channel.name}",
                                       overwrites={everyone_role: everyone_perms, archives_role: archive_perms},
                                       category=archive_category)

                propaganda_channel = discord.utils.get(self.bot.dciv.text_channels,
                                                       name="propaganda")

                if propaganda_channel is not None:
                    await propaganda_channel.edit(name=f"mk{self.bot.mk.MARK}-propaganda", category=archive_category,
                                                  overwrites={everyone_role: everyone_perms,
                                                              archives_role: archive_perms})

                press_channel = discord.utils.get(self.bot.dciv.text_channels,
                                                  name="press")

                if press_channel is not None:
                    await press_channel.edit(name=f"mk{self.bot.mk.MARK}-press", category=archive_category,
                                                  overwrites={everyone_role: everyone_perms,
                                                              archives_role: archive_perms})

                await ctx.send(":white_check_mark: Done.")


def setup(bot):
    bot.add_cog(Moderation(bot))
