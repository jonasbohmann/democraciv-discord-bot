import config
import discord
import datetime

from discord.ext import commands


# -- logging.py | event.logging --
#
# Logging module.
#


class Log(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # -- Message Events --

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        guild = before.guild

        if before.content == after.content:
            return
        if config.getGuildConfig(guild.id)['enableLogging']:
            if str(before.channel.id) not in config.getGuildConfig(guild.id)['excludedChannelsFromLogging']:
                if not before.clean_content or not after.clean_content:  # Removing this throws a http
                    # 400 bad request exception
                    return
                elif before.clean_content and after.clean_content:
                    channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
                    embed = self.bot.embeds.embed_builder(title=':pencil2: Message Edited', description="", time_stamp=True)
                    embed.add_field(name='Author',
                                    value=before.author.mention + ' ' + before.author.name + '#'
                                          + before.author.discriminator,
                                    inline=True)
                    embed.add_field(name='Channel', value=before.channel.mention, inline=True)
                    embed.add_field(name='Before', value=before.clean_content, inline=False)
                    embed.add_field(name='After', value=after.clean_content, inline=False)
                    await channel.send(embed=embed)
            else:
                return
        return

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        guild = message.guild

        if config.getGuildConfig(guild.id)['enableLogging']:
            if str(message.channel.id) not in config.getGuildConfig(guild.id)['excludedChannelsFromLogging']:
                channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
                embed = self.bot.embeds.embed_builder(title=':wastebasket: Message Deleted', description="", time_stamp=True)
                embed.add_field(name='Author',
                                value=message.author.mention + ' ' + message.author.name + '#'
                                      + message.author.discriminator,
                                inline=True)
                embed.add_field(name='Channel', value=message.channel.mention, inline=True)

                if not message.embeds:
                    # If the deleted message is an embed, sending this new embed will raise an error as
                    # message.clean_content does not work with embeds
                    embed.add_field(name='Message', value=message.clean_content, inline=False)

                await channel.send(embed=embed)
            else:
                return
        return

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload):
        guild = self.bot.get_guild(payload.guild_id)

        if config.getGuildConfig(guild.id)['enableLogging']:
            if str(payload.channel_id) not in config.getGuildConfig(guild.id)['excludedChannelsFromLogging']:
                channel = self.bot.get_channel(payload.channel_id)
                log_channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
                embed = self.bot.embeds.embed_builder(title=':wastebasket: :wastebasket: Bulk of Messages Deleted',
                                                      description="")
                embed.add_field(name='Amount',
                                value=f'{len(payload.message_ids)}\n', inline=True)
                embed.add_field(name='Channel',
                                value=channel.mention, inline=True)

                await log_channel.send(embed=embed)
            else:
                return
        return

    # -- Member Events --

    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild = member.guild
        log_channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])

        if config.getGuildConfig(guild.id)['enableWelcomeMessage']:
            welcome_channel = discord.utils.get(guild.text_channels,
                                                name=config.getGuildConfig(guild.id)['welcomeChannel'])

            # Apparently this doesn't raise an error if {member} is not in welcome_message
            welcome_message = config.getStrings(guild.id)['welcomeMessage'].format(member=member.mention)
            await welcome_channel.send(welcome_message)

        if config.getGuildConfig(guild.id)['enableDefaultRole']:
            default_role = discord.utils.get(guild.roles, name=config.getGuildConfig(guild.id)['defaultRole'])

            try:
                await member.add_roles(default_role)
            except discord.Forbidden:
                try:
                    await log_channel.send(f":x: Missing permissions to add default role to {member}.")
                except Exception:
                    pass

        if config.getGuildConfig(guild.id)['enableLogging']:
            embed = self.bot.embeds.embed_builder(title=':tada: Member Joined', description="", time_stamp=True)
            embed.add_field(name='Member', value=member.mention)
            embed.add_field(name='Name', value=member.name + '#' + member.discriminator)
            embed.add_field(name='ID', value=member.id)
            embed.add_field(name='Mobile', value=member.is_on_mobile())
            embed.set_thumbnail(url=member.avatar_url)
            
            await log_channel.send(embed=embed)

        return

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        guild = member.guild

        if config.getGuildConfig(guild.id)['enableLogging']:
            channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
            embed = self.bot.embeds.embed_builder(title=':no_pedestrians: Member Left', description="", time_stamp=True)
            embed.add_field(name='Name', value=member.name + '#' + member.discriminator)
            embed.set_thumbnail(url=member.avatar_url)
            
            await channel.send(embed=embed)
        return

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        guild = before.guild

        if config.getGuildConfig(guild.id)['enableLogging']:
            if before.display_name != after.display_name:
                log_channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
                embed = self.bot.embeds.embed_builder(title=':arrows_counterclockwise: Nickname Changed',
                                                      description="")
                embed.add_field(name='Member', value=before.mention + ' ' + before.name + '#' + before.discriminator,
                                inline=False)
                embed.add_field(name='Before', value=before.display_name)
                embed.add_field(name='After', value=after.display_name)
                embed.set_thumbnail(url=before.avatar_url)
                
                await log_channel.send(embed=embed)

            if before.roles != after.roles:

                if len(before.roles) < len(after.roles):
                    for x in after.roles:
                        if x not in before.roles:
                            given_role = x.name
                    guild = before.guild
                    log_channel = discord.utils.get(guild.text_channels,
                                                    name=config.getGuildConfig(guild.id)['logChannel'])
                    embed = self.bot.embeds.embed_builder(title=':sunglasses: Role given to Member', description="", time_stamp=True)
                    embed.add_field(name='Member',
                                    value=before.mention + ' ' + before.name + '#' + before.discriminator,
                                    inline=False)
                    embed.add_field(name='Role', value=given_role)
                    embed.set_thumbnail(url=before.avatar_url)
                    
                    await log_channel.send(embed=embed)

                if len(before.roles) > len(after.roles):
                    for x in before.roles:
                        if x not in after.roles:
                            removed_role = x.name
                    guild = before.guild
                    log_channel = discord.utils.get(guild.text_channels,
                                                    name=config.getGuildConfig(guild.id)['logChannel'])
                    embed = self.bot.embeds.embed_builder(title=':zipper_mouth: Role removed from Member',
                                                          description="")
                    embed.add_field(name='Member',
                                    value=before.mention + ' ' + before.name + '#' + before.discriminator,
                                    inline=False)
                    embed.add_field(name='Role', value=removed_role)
                    embed.set_thumbnail(url=before.avatar_url)
                    
                    await log_channel.send(embed=embed)
            else:
                return
        return

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        if config.getGuildConfig(guild.id)['enableLogging']:
            channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
            embed = self.bot.embeds.embed_builder(title=':no_entry: Member Banned', description="", time_stamp=True)
            embed.add_field(name='Member', value=user.mention)
            embed.add_field(name='Name', value=user.name + '#' + user.discriminator)
            embed.set_thumbnail(url=user.avatar_url)
            
            await channel.send(embed=embed)
        return

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        if config.getGuildConfig(guild.id)['enableLogging']:
            channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
            embed = self.bot.embeds.embed_builder(title=':dove: Member Unbanned', description="", time_stamp=True)
            embed.add_field(name='Member', value=user.mention)
            embed.add_field(name='Name', value=user.name + '#' + user.discriminator)
            embed.set_thumbnail(url=user.avatar_url)
            
            await channel.send(embed=embed)
        return

    # -- Guild Events --

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        introduction_channel = guild.text_channels[0]

        # Alert owner of this bot that the bot was invited to some place
        await self.bot.DerJonas_dm_channel.send(f":warning: I was added to {guild.name} ({guild.id}). Here are some invites:")

        # Get invite for new guild to send to owner_dm_channel
        guild_invites = await guild.invites()
        try:
            guild_invite_1 = str(guild_invites[0])
            await self.bot.DerJonas_dm_channel.send(guild_invite_1)
        except IndexError as e:
            pass

        # Send introduction message to random guild channel
        embed = self.bot.embeds.embed_builder(title=':two_hearts: Hey there!',
                                              description=f"Thanks for inviting me!\n\nYou can check "
                                                          f"`-help` to get some more information "
                                                          f"about me.\n\nUse the `-guild` command to "
                                                          f"configure me for this guild.\n\nIf you "
                                                          f"have any questions or suggestions, "
                                                          f"send a DM to {self.bot.DerJonas_object.mention}!")

        # Add new guild to guilds.json
        success = config.initializeNewGuild(guild)

        if success:
            await introduction_channel.send(embed=embed)

        elif not success:
            await introduction_channel.send(f":x: Unexpected error occurred while initializing this guild.\n"
                                            f"Help me {self.bot.DerJonas_object.mention} :worried:")

        return

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        guild = role.guild

        # Handle exception if bot was just added to new guild
        try:
            if config.getGuildConfig(guild.id)['enableLogging']:
                log_channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
                embed = self.bot.embeds.embed_builder(title=':new: Role Created', description="", time_stamp=True)
                embed.add_field(name='Role', value=role.name)
                embed.add_field(name='Colour', value=role.colour)
                embed.add_field(name='ID', value=role.id, inline=False)
                
                await log_channel.send(embed=embed)
            return
        except TypeError:
            return

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        guild = role.guild

        if config.getGuildConfig(guild.id)['enableLogging']:
            log_channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
            embed = self.bot.embeds.embed_builder(title=':exclamation: Role Deleted', description="", time_stamp=True)
            embed.add_field(name='Role', value=role.name)
            embed.add_field(name='Creation Date',
                            value=datetime.datetime.strftime(role.created_at, "%d.%m.%Y, %H:%M:%S"))
            embed.add_field(name='ID', value=role.id, inline=False)
            
            await log_channel.send(embed=embed)
        return

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        guild = channel.guild

        if config.getGuildConfig(guild.id)['enableLogging']:
            log_channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
            embed = self.bot.embeds.embed_builder(title=':new: Channel Created', description="", time_stamp=True)
            embed.add_field(name='Name', value=channel.mention)
            embed.add_field(name='Category', value=channel.category)
            
            await log_channel.send(embed=embed)
        return

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        guild = channel.guild

        if config.getGuildConfig(guild.id)['enableLogging']:
            log_channel = discord.utils.get(guild.text_channels, name=config.getGuildConfig(guild.id)['logChannel'])
            embed = self.bot.embeds.embed_builder(title=':exclamation: Channel Deleted', description="", time_stamp=True)
            embed.add_field(name='Name', value=channel.name)
            embed.add_field(name='Category', value=channel.category)
            
            await log_channel.send(embed=embed)
        return


def setup(bot):
    bot.add_cog(Log(bot))
