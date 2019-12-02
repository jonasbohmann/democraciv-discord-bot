import discord
import datetime

import util.utils as utils

from discord.ext import commands


# -- logging.py | event.logging --
#
# Logging module.
#


class Log(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def log_event(self, guild: discord.Guild, title: str, fields: dict, thumbnail: str = None,
                        to_owner: bool = False):

        embed = self.bot.embeds.embed_builder(title=title, description="", time_stamp=True)

        for field in fields:
            embed.add_field(name=field, value=fields[field][0], inline=fields[field][1])

        if thumbnail is not None:
            embed.set_thumbnail(url=thumbnail)

        # Send event embed to log channel
        log_channel = await utils.get_logging_channel(self.bot, guild.id)

        if log_channel is not None:
            await log_channel.send(embed=embed)

        # Send event embed to author DM
        if to_owner:
            embed.add_field(name='Guild', value=f"{guild.name} ({guild.id})", inline=False)
            await self.bot.DerJonas_object.send(embed=embed)

    async def is_channel_excluded(self, guild_id, channel_id):
        excluded_channels = (await self.bot.db.fetchrow("SELECT logging_excluded FROM guilds WHERE id = $1"
                                                        , guild_id))['logging_excluded']

        if excluded_channels is not None:
            return channel_id in excluded_channels
        else:
            return False

    # -- Message Events --

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if isinstance(before.channel, discord.DMChannel):
            return

        if not await self.bot.checks.is_logging_enabled(before.guild.id):
            return

        if not await self.is_channel_excluded(before.guild.id, before.channel.id):
            if not before.clean_content or not after.clean_content:
                # Removing this throws a http 400 bad request exception
                return

            if before.content == after.content:
                return

            elif before.clean_content and after.clean_content:
                embed_fields = {
                    "Author": [f"{before.author.mention} {before.author.name}#{before.author.discriminator}", False],
                    "Channel": [f"{before.channel.mention}", True],
                    "Before": [f"{before.clean_content}", False],
                    "After": [f"{after.clean_content}", False]
                }
                await self.log_event(before.guild, ":pencil2: Message Edited", embed_fields, to_owner=False)

        else:
            return

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if isinstance(message.channel, discord.DMChannel):
            return

        if not await self.bot.checks.is_logging_enabled(message.guild.id):
            return

        if not await self.is_channel_excluded(message.guild.id, message.channel.id):
            embed_fields = {
                "Author": [f"{message.author.mention} {message.author.name}#{message.author.discriminator}", True],
                "Channel": [f"{message.channel.mention}", False]
            }

            if not message.embeds:
                # If the deleted message is an embed, sending this new embed will raise an error as
                # message.clean_content does not work with embeds
                embed_fields['Message'] = [message.clean_content, False]

            await self.log_event(message.guild, ':wastebasket: Message Deleted', embed_fields, to_owner=False)

        else:
            return

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload):
        guild = self.bot.get_guild(payload.guild_id)

        if not await self.bot.checks.is_logging_enabled(guild.id):
            return

        if not await self.is_channel_excluded(guild.id, payload.channel_id):
            channel = self.bot.get_channel(payload.channel_id)

            embed_fields = {
                "Amount": [f"{len(payload.message_ids)}\n", True],
                "Channel": [f"{channel.mention}", True]
            }

            await self.log_event(guild, ':wastebasket: :wastebasket: Bulk of Messages Deleted', embed_fields,
                                 to_owner=False)

        else:
            return

    # -- Member Events --

    @commands.Cog.listener()
    async def on_member_join(self, member):
        welcome_channel = await utils.get_welcome_channel(self.bot, member.guild.id)

        if welcome_channel is not None:
            if await self.bot.checks.is_welcome_message_enabled(member.guild.id):
                # Apparently this doesn't raise an error if {member} is not in welcome_message
                welcome_message = (await self.bot.db.fetchrow("SELECT welcome_message FROM guilds WHERE id = $1",
                                                              member.guild.id))['welcome_message']. \
                    format(member=member.mention)
                await welcome_channel.send(welcome_message)

            if await self.bot.checks.is_default_role_enabled(member.guild.id):

                default_role = (await self.bot.db.fetchrow("SELECT defaultrole_role FROM guilds WHERE id = $1",
                                                           member.guild.id))['defaultrole_role']
                default_role = member.guild.get_role(default_role)

                if default_role is not None:
                    try:
                        await member.add_roles(default_role)
                    except discord.Forbidden:
                        await welcome_channel.send(f":x: Missing permissions to add default role to {member.name}.")

        if not await self.bot.checks.is_logging_enabled(member.guild.id):
            return

        embed_fields = {
            "Member": [member.mention, True],
            "Name": [f"{member.name} #{member.discriminator}", True],
            "Mobile": [f"{member.is_on_mobile()}", True],
            "ID": [f"{member.id}", False]
        }

        await self.log_event(member.guild, ':tada: Member Joined', embed_fields, thumbnail=member.avatar_url,
                             to_owner=False)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        if not await self.bot.checks.is_logging_enabled(member.guild.id):
            return

        embed_fields = {
            "Name": [f"{member.name} #{member.discriminator}", True]
        }

        await self.log_event(member.guild, ':no_pedestrians: Member Left', embed_fields, thumbnail=member.avatar_url,
                             to_owner=False)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if not await self.bot.checks.is_logging_enabled(before.guild.id):
            return

        if before.display_name != after.display_name:
            embed_fields = {
                "Member": [f"{before.mention} {before.name}#{before.discriminator}", False],
                "Before": [before.display_name, False],
                "After": [after.display_name, False]

            }

            await self.log_event(before.guild, ':arrows_counterclockwise: Nickname Changed', embed_fields,
                                 thumbnail=before.avatar_url, to_owner=False)

        if before.roles != after.roles:

            if len(before.roles) < len(after.roles):
                for x in after.roles:
                    if x not in before.roles:
                        given_role = x.name

                embed_fields = {
                    "Member": [f"{before.mention} {before.name}#{before.discriminator}", False],
                    "Role": [given_role, False]
                }

                await self.log_event(before.guild, ':sunglasses: Role given to Member', embed_fields,
                                     thumbnail=before.avatar_url, to_owner=False)

            if len(before.roles) > len(after.roles):
                for x in before.roles:
                    if x not in after.roles:
                        removed_role = x.name

                embed_fields = {
                    "Member": [f"{before.mention} {before.name}#{before.discriminator}", False],
                    "Role": [removed_role, False]
                }

                await self.log_event(before.guild, ':zipper_mouth: Role removed from Member', embed_fields,
                                     thumbnail=before.avatar_url, to_owner=False)

            else:
                return

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        if not await self.bot.checks.is_logging_enabled(guild.id):
            return

        embed_fields = {
            "Name": [f"{user.name} #{user.discriminator}", True]
        }

        await self.log_event(guild, ':no_entry: Member Banned', embed_fields, thumbnail=user.avatar_url,
                             to_owner=True)

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        if not await self.bot.checks.is_logging_enabled(guild.id):
            return

        embed_fields = {
            "Name": [f"{user.name} #{user.discriminator}", True]
        }

        await self.log_event(guild, ':dove: Member Unbanned', embed_fields, thumbnail=user.avatar_url,
                             to_owner=True)

    # -- Guild Events --

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        introduction_channel = guild.text_channels[0]

        # Alert owner of this bot that the bot was invited to some place
        await self.bot.DerJonas_object.send(
            f":warning: I was added to {guild.name} ({guild.id}). Here are some invites:")

        # Get invite for new guild to send to owner_dm_channel
        try:
            guild_invites = await guild.invites()
            guild_invite_1 = str(guild_invites[0])
            await self.bot.DerJonas_object.send(guild_invite_1)
        except (IndexError, discord.Forbidden):
            pass

        # Send introduction message to random guild channel
        embed = self.bot.embeds.embed_builder(title=':two_hearts: Hey there!',
                                              description=f"Thanks for inviting me!\n\nYou can check "
                                                          f"`-help` to get some more information "
                                                          f"about me.\n\nUse the `-guild` command to "
                                                          f"configure me for this guild.\n\nIf you "
                                                          f"have any questions or suggestions, "
                                                          f"send a DM to {self.bot.DerJonas_object.mention}!")

        # Add new guild to database
        status = await self.bot.db.execute("INSERT INTO guilds (id, welcome, logging, logging_excluded, defaultrole) "
                                           "VALUES ($1, false, false, ARRAY[0], false)", guild.id)

        if status == "INSERT 0 1":
            try:
                await introduction_channel.send(embed=embed)
            except discord.Forbidden:
                print(f"[BOT] Got Forbidden while sending my introduction message on {guild.name} ({guild.id})")

        elif not status:
            try:
                await introduction_channel.send(f":x: Unexpected error occurred while initializing this guild.\n\n"
                                                f"Help me {self.bot.DerJonas_object.mention} :worried:")
            except discord.Forbidden:
                print(f"[BOT] Got Forbidden while sending my introduction message on {guild.name} ({guild.id})")

        return

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        if not await self.bot.checks.is_logging_enabled(role.guild.id):
            return

        # Handle exception if bot was just added to new guild
        try:
            embed_fields = {
                "Role": [role.name, True],
                "Colour": [role.colour, True],
                "ID": [role.id, False]
            }

            await self.log_event(role.guild, ':new: Role Created', embed_fields, to_owner=False)

        except TypeError:
            return

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        if not await self.bot.checks.is_logging_enabled(role.guild.id):
            return

        embed_fields = {
            "Role": [role.name, True],
            "Creation Date": [datetime.datetime.strftime(role.created_at, "%d.%m.%Y, %H:%M:%S"), True],
            "ID": [role.id, False]
        }

        await self.log_event(role.guild, ':exclamation: Role Deleted', embed_fields, to_owner=False)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        if not await self.bot.checks.is_logging_enabled(channel.guild.id):
            return

        embed_fields = {
            "Name": [channel.mention, True],
            "Category": [channel.category, True]
        }

        await self.log_event(channel.guild, ':new: Channel Created', embed_fields, to_owner=False)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if not await self.bot.checks.is_logging_enabled(channel.guild.id):
            return

        embed_fields = {
            "Name": [channel.name, True],
            "Category": [channel.category, True]
        }

        await self.log_event(channel.guild, ':exclamation: Channel Deleted', embed_fields, to_owner=False)


def setup(bot):
    bot.add_cog(Log(bot))
