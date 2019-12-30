import discord

from util import utils, mk
from config import config, token

from discord.ext import commands


class Moderation(commands.Cog):
    """Commands for the Mod Team"""

    def __init__(self, bot):
        self.bot = bot
        self.mod_request_channel = mk.MOD_REQUESTS_CHANNEL

    @commands.Cog.listener(name="on_message")
    async def mod_request_listener(self, message):
        if message.channel.id != self.mod_request_channel:
            return

        if mk.get_moderation_role(self.bot) not in message.role_mentions:
            return

        embed = self.bot.embeds.embed_builder(title=":grey_exclamation: New Request in #mod-requests",
                                              description=f"[Jump to message.]"
                                                          f"({message.jump_url}"
                                                          f")")
        embed.add_field(name="From", value=message.author.mention)
        embed.add_field(name="Request", value=message.content, inline=False)

        await mk.get_moderation_notifications_channel(self.bot).send(content=mk.get_moderation_role(self.bot).mention,
                                                                     embed=embed)

    @commands.command(name='hub', aliases=['modhub', 'moderationhub', 'mhub'])
    @commands.has_role("Moderation")
    @utils.is_democraciv_guild()
    async def hub(self, ctx):
        """Link to the Moderation Hub"""
        link = token.MOD_HUB or 'Link not provided.'
        embed = self.bot.embeds.embed_builder(title="Moderation Hub", description=f"[Link]({link})")
        await ctx.message.add_reaction("\U0001f4e9")
        await ctx.author.send(embed=embed)

    @commands.command(name='registry')
    @commands.has_role("Moderation")
    @utils.is_democraciv_guild()
    async def registry(self, ctx):
        """Link to the Democraciv Registry"""
        link = token.REGISTRY or 'Link not provided.'
        embed = self.bot.embeds.embed_builder(title="Democraciv Registry", description=f"[Link]({link})")
        await ctx.message.add_reaction("\U0001f4e9")
        await ctx.author.send(embed=embed)

    @commands.command(name='drive', aliases=['googledrive', 'gdrive'])
    @commands.has_role("Moderation")
    @utils.is_democraciv_guild()
    async def gdrive(self, ctx):
        """Link to the Google Drive for MK6"""
        link = token.MK6_DRIVE or 'Link not provided.'
        embed = self.bot.embeds.embed_builder(title="Google Drive for MK6", description=f"[Link]({link})")
        await ctx.message.add_reaction("\U0001f4e9")
        await ctx.author.send(embed=embed)

    @commands.command(name='elections', aliases=['election', 'pins', 'electiontool', 'pintool'])
    @commands.has_role("Moderation")
    @utils.is_democraciv_guild()
    async def electiontool(self, ctx):
        """Link to DerJonas' Election Tool"""
        link = token.PIN_TOOL or 'Link not provided.'
        embed = self.bot.embeds.embed_builder(title="DerJonas' Election Tool", description=f"[Link]({link})")
        await ctx.message.add_reaction("\U0001f4e9")
        await ctx.author.send(embed=embed)

    @commands.command(name='kick')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = None):
        """Kick a member"""
        if member == ctx.author:
            return await ctx.send(":x: You can't kick yourself.")

        if member == self.bot.DerJonas_object:
            #  :)
            return await ctx.send(":x: You can't kick that person.")

        if member == ctx.guild.me:
            return await ctx.send(":x: You can't kick me.")

        if reason:
            formatted_reason = f"Action requested by {ctx.author} with reason: {reason}"
        else:
            formatted_reason = f"Action requested by {ctx.author} with no specified reason."

        try:
            await ctx.guild.kick(member, reason=formatted_reason)
        except discord.Forbidden:
            return await ctx.send(":x: I'm not allowed to kick that person.")

        try:
            await member.send(f":no_entry: You were kicked from {ctx.guild.name}.")
        except discord.Forbidden:
            pass

        await ctx.send(f":white_check_mark: Successfully kicked {member}!")

    @commands.command(name='ban')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: str, *, reason: str = None):
        """Ban a member

        If you want to ban a user that is not on this guild, use the user's ID: `-ban <id>`."""

        try:
            member_object = await commands.MemberConverter().convert(ctx, member)
            member_id = member_object.id
        except commands.BadArgument:
            try:
                member_id = int(member)
            except ValueError:
                member_id = None
            member_object = None

        if member_id is None:
            return await ctx.send(":x: I couldn't find that person.")

        if member_object == ctx.author:
            return await ctx.send(":x: You can't ban yourself.")

        if member_object == self.bot.DerJonas_object:
            #  :)
            return await ctx.send(":x: You can't ban that person.")

        if member_object == ctx.guild.me:
            return await ctx.send(":x: You can't ban me.")

        if reason:
            formatted_reason = f"Action requested by {ctx.author} with reason: {reason}"
        else:
            formatted_reason = f"Action requested by {ctx.author} with no specified reason."

        try:
            await ctx.guild.ban(discord.Object(id=member_id), reason=formatted_reason, delete_message_days=0)
        except discord.Forbidden:
            return await ctx.send(":x: I'm not allowed to ban that person.")
        except discord.HTTPException as e:
            return await ctx.send(":x: I couldn't find that person.")

        if member_object:
            try:
                await member_object.send(f":no_entry: You were banned from {ctx.guild.name}.")
            except discord.Forbidden:
                pass

        await ctx.send(f":white_check_mark: Successfully banned {member}!")

    @ban.error
    async def banerror(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(":x: I couldn't find that person.")

    @commands.command(name='unban')
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, member: discord.User, *, reason: str = None):
        """Unban a member"""

        if reason:
            formatted_reason = f"Action requested by {ctx.author} with reason: {reason}"
        else:
            formatted_reason = f"Action requested by {ctx.author} with no specified reason."

        try:
            await ctx.guild.unban(discord.Object(id=member.id), reason=formatted_reason)
        except discord.Forbidden:
            return await ctx.send(":x: I'm not allowed to unban that person.")
        except discord.HTTPException:
            return await ctx.send(":x: That person is not banned.")

        await ctx.send(f":white_check_mark: Successfully unbanned {member}!")

    @unban.error
    async def unbanerror(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(":x: I couldn't find that person.")


def setup(bot):
    bot.add_cog(Moderation(bot))
