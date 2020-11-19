from discord.ext import commands

from config import config
from utils import context, text


class Profile(context.CustomCog):

    async def ensure_dm_settings(self, user: int):
        settings = await self.bot.db.fetchrow("SELECT * FROM dm_settings WHERE user_id = $1", user)

        if not settings:
            settings = await self.bot.db.fetchrow("INSERT INTO dm_settings (user_id) VALUES ($1) RETURNING *", user)

        return settings

    async def toggle_dm_setting(self, user: int, setting: str):
        settings = await self.ensure_dm_settings(user)
        current_setting = settings[setting]
        await self.bot.db.execute(f"UPDATE dm_settings SET {setting} = $1 WHERE user_id = $2",
                                  not current_setting,
                                  user)
        return not current_setting

    @commands.group(name='dms', aliases=['dm', 'pm', 'dmsettings', 'dm-settings', 'dmsetting'], case_insensitive=True,
                    invoke_without_command=True)
    async def dmsettings(self, ctx):
        """See your currently enabled DMs from me"""

        emojify_settings = self.bot.get_cog("Server").emojify_settings
        settings = await self.ensure_dm_settings(ctx.author.id)

        mute_kick_ban = emojify_settings(settings['ban_kick_mute'])
        leg_session_open = emojify_settings(settings['leg_session_open'])
        leg_session_update = emojify_settings(settings['leg_session_update'])
        leg_session_submit = emojify_settings(settings['leg_session_submit'])
        leg_session_withdraw = emojify_settings(settings['leg_session_withdraw'])

        embed = text.SafeEmbed(title=f"DMs for {ctx.author.name}",
                               description=f"Check `{config.BOT_PREFIX}help dms` for help on "
                                           f"how to enable or disable these settings.\n\n"
                                           f"{mute_kick_ban} DM when you get muted, kicked or banned\n"
                                           f"{leg_session_open} "
                                           f"*({self.bot.mk.LEGISLATURE_LEGISLATOR_NAME} Only)* DM when "
                                           f"a {self.bot.mk.LEGISLATURE_ADJECTIVE} Session opens\n"
                                           f"{leg_session_update} "
                                           f"*({self.bot.mk.LEGISLATURE_LEGISLATOR_NAME} Only)* DM when "
                                           f"voting starts for a {self.bot.mk.LEGISLATURE_ADJECTIVE} Session\n"
                                           f"{leg_session_submit} "
                                           f"*({self.bot.mk.LEGISLATURE_CABINET_NAME} Only)* DM when "
                                           f"someone submits a Bill or Motion\n"
                                           f"{leg_session_withdraw} "
                                           f"*({self.bot.mk.LEGISLATURE_CABINET_NAME} Only)* DM when "
                                           f"someone withdraws a Bill or Motion\n")
        await ctx.send(embed=embed)

    @dmsettings.command(name='enableall')
    async def enableall(self, ctx):
        """Enable all DMs"""

        await self.ensure_dm_settings(ctx.author.id)

        await self.bot.db.execute("UPDATE dm_settings SET"
                                  " ban_kick_mute = true, leg_session_open = true,"
                                  " leg_session_update = true, leg_session_submit = true,"
                                  " leg_session_withdraw = true"
                                  " WHERE user_id = $1", ctx.author.id)

        await ctx.send(":white_check_mark: All DMs from me are now enabled.")

    @dmsettings.command(name='disableall')
    async def disableall(self, ctx):
        """Disable all DMs"""

        await self.ensure_dm_settings(ctx.author.id)

        await self.bot.db.execute("UPDATE dm_settings SET"
                                  " ban_kick_mute = false, leg_session_open = false,"
                                  " leg_session_update = false, leg_session_submit = false,"
                                  " leg_session_withdraw = false"
                                  " WHERE user_id = $1", ctx.author.id)

        await ctx.send(":white_check_mark: All DMs from me are now disabled.")

    @dmsettings.command(name='moderation', aliases=['mod', 'kick', 'ban', 'mute'])
    async def moderation(self, ctx):
        """Toggle DMs for when you get muted, kicked or banned"""

        new_value = await self.toggle_dm_setting(ctx.author.id, "ban_kick_mute")

        if new_value:
            message = ":white_check_mark: You will now receive DMs when you get muted, kicked or banned by me."
        else:
            message = ":white_check_mark: You will no longer receive DMs when you get muted, kicked or banned."

        await ctx.send(message)

    @dmsettings.command(name='legsessionopen')
    async def legsessionopen(self, ctx):
        """Toggle DMs for when a Legislative Session opens"""

        new_value = await self.toggle_dm_setting(ctx.author.id, "leg_session_open")

        if new_value:
            message = f":white_check_mark: You will now receive DMs when you " \
                      f"are a {self.bot.mk.LEGISLATURE_LEGISLATOR_NAME} " \
                      f"and a new Legislative Session is opened."
        else:
            message = f":white_check_mark: You will no longer receive DMs when you are " \
                      f"a {self.bot.mk.LEGISLATURE_LEGISLATOR_NAME} " \
                      f"and a new Legislative Session is opened."

        await ctx.send(message)

    @dmsettings.command(name='legsessionvoting')
    async def legsessionvoting(self, ctx):
        """Toggle DMs for when voting starts for a Legislative Session"""

        new_value = await self.toggle_dm_setting(ctx.author.id, "leg_session_update")

        if new_value:
            message = f":white_check_mark: You will now receive DMs when you are " \
                      f"a {self.bot.mk.LEGISLATURE_LEGISLATOR_NAME} " \
                      f"and voting starts for a Legislative Session."
        else:
            message = f":white_check_mark: You will no longer receive DMs when you are " \
                      f"a {self.bot.mk.LEGISLATURE_LEGISLATOR_NAME} " \
                      f"and voting starts for a Legislative Session."

        await ctx.send(message)

    @dmsettings.command(name='legsubmit')
    async def legsubmit(self, ctx):
        """Toggle DMs for when someone submits a Bill or Motion"""

        new_value = await self.toggle_dm_setting(ctx.author.id, "leg_session_submit")

        if new_value:
            message = f":white_check_mark: You will now receive DMs when you are a member of the " \
                      f"{self.bot.mk.LEGISLATURE_CABINET_NAME} " \
                      f"and someone submits a Bill or Motion. " \
                      f"Note that you will never get a DM when a member of the " \
                      f"{self.bot.mk.LEGISLATURE_CABINET_NAME} is the one submitting."
        else:
            message = f":white_check_mark: You will no longer receive DMs when you are a member of the " \
                      f"{self.bot.mk.LEGISLATURE_CABINET_NAME} and someone submits a Bill or Motion."

        await ctx.send(message)

    @dmsettings.command(name='legwithdraw')
    async def legwithdraw(self, ctx):
        """Toggle DMs for when someone withdraws a Bill or Motion"""

        new_value = await self.toggle_dm_setting(ctx.author.id, "leg_session_withdraw")

        if new_value:
            message = f":white_check_mark: You will now receive DMs when you are a member of the " \
                      f"{self.bot.mk.LEGISLATURE_CABINET_NAME} and someone withdraws their Bill or Motion. " \
                      f"Note that you will never get a DM when a member of the " \
                      f"{self.bot.mk.LEGISLATURE_CABINET_NAME} is the one withdrawing."

        else:
            message = f":white_check_mark: You will no longer receive DMs when you are a member of the " \
                      f"{self.bot.mk.LEGISLATURE_CABINET_NAME} and someone withdraws their Bill or Motion."

        await ctx.send(message)


def setup(bot):
    bot.add_cog(Profile(bot))