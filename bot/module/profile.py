from discord.ext import commands

from bot.config import config
from bot.utils import context, text


class Profile(context.CustomCog):
    """Organize personal settings"""
    async def ensure_dm_settings(self, user: int):
        settings = await self.bot.db.fetchrow("SELECT * FROM dm_setting WHERE user_id = $1", user)

        if not settings:
            settings = await self.bot.db.fetchrow("INSERT INTO dm_setting (user_id) VALUES ($1) RETURNING *", user)

        return settings

    async def toggle_dm_setting(self, user: int, setting: str):
        settings = await self.ensure_dm_settings(user)
        current_setting = settings[setting]
        await self.bot.db.execute(
            f"UPDATE dm_setting SET {setting} = $1 WHERE user_id = $2",
            not current_setting,
            user,
        )
        return not current_setting

    @commands.group(
        name="dms",
        aliases=["dm", "pm", "dmsettings", "dm-settings", "dmsetting"],
        case_insensitive=True,
        invoke_without_command=True,
    )
    async def dmsettings(self, ctx):
        """See your currently enabled DMs from me"""

        emojify_settings = self.bot.get_cog("Server").emojify_settings
        settings = await self.ensure_dm_settings(ctx.author.id)

        mute_kick_ban = emojify_settings(settings["ban_kick_mute"])
        leg_session_open = emojify_settings(settings["leg_session_open"])
        leg_session_update = emojify_settings(settings["leg_session_update"])
        leg_session_submit = emojify_settings(settings["leg_session_submit"])
        leg_session_withdraw = emojify_settings(settings["leg_session_withdraw"])
        party = emojify_settings(settings["party_join_leave"])

        embed = text.SafeEmbed(
            description=f"Check `{config.BOT_PREFIX}help dms` for help on "
            f"how to enable or disable each setting.\n\n"
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
            f"someone withdraws a Bill or Motion\n"
            f"{party} *(Party Leaders Only)* DM when someone joins or leaves your political party\n"
        )

        embed.set_author(name=ctx.author, icon_url=ctx.author_icon)
        await ctx.send(embed=embed)

    @dmsettings.command(name="on", aliases=['enableall'])
    async def enableall(self, ctx):
        """Enable all DMs"""

        await self.ensure_dm_settings(ctx.author.id)

        await self.bot.db.execute(
            "UPDATE dm_setting SET"
            " ban_kick_mute = true, leg_session_open = true,"
            " leg_session_update = true, leg_session_submit = true,"
            " leg_session_withdraw = true, party_join_leave = true"
            " WHERE user_id = $1",
            ctx.author.id,
        )

        await ctx.send(f"{config.YES} All DMs from me are now enabled.")

    @dmsettings.command(name="off", aliases=["disableall"])
    async def disableall(self, ctx):
        """Disable all DMs"""

        await self.ensure_dm_settings(ctx.author.id)

        await self.bot.db.execute(
            "UPDATE dm_setting SET"
            " ban_kick_mute = false, leg_session_open = false,"
            " leg_session_update = false, leg_session_submit = false,"
            " leg_session_withdraw = false, party_join_leave = false "
            " WHERE user_id = $1",
            ctx.author.id,
        )

        await ctx.send(f"{config.YES} All DMs from me are now disabled.")

    @dmsettings.command(name="moderation", aliases=["mod", "kick", "ban", "mute"])
    async def moderation(self, ctx):
        """Toggle DMs for when you get muted, kicked or banned"""

        new_value = await self.toggle_dm_setting(ctx.author.id, "ban_kick_mute")

        if new_value:
            message = f"{config.YES} You will now receive DMs when you get muted, kicked or banned by me."
        else:
            message = f"{config.YES} You will no longer receive DMs when you get muted, kicked or banned."

        await ctx.send(message)

    @dmsettings.command(name="legsessionopen")
    async def legsessionopen(self, ctx):
        """Toggle DMs for when a Legislative Session opens"""

        new_value = await self.toggle_dm_setting(ctx.author.id, "leg_session_open")

        if new_value:
            message = (
                f"{config.YES} You will now receive DMs when you "
                f"are a {self.bot.mk.LEGISLATURE_LEGISLATOR_NAME} "
                f"and a new Legislative Session is opened."
            )
        else:
            message = (
                f"{config.YES} You will no longer receive DMs when you are "
                f"a {self.bot.mk.LEGISLATURE_LEGISLATOR_NAME} "
                f"and a new Legislative Session is opened."
            )

        await ctx.send(message)

    @dmsettings.command(name="legsessionvoting")
    async def legsessionvoting(self, ctx):
        """Toggle DMs for when voting starts for a Legislative Session"""

        new_value = await self.toggle_dm_setting(ctx.author.id, "leg_session_update")

        if new_value:
            message = (
                f"{config.YES} You will now receive DMs when you are "
                f"a {self.bot.mk.LEGISLATURE_LEGISLATOR_NAME} "
                f"and voting starts for a Legislative Session."
            )
        else:
            message = (
                f"{config.YES} You will no longer receive DMs when you are "
                f"a {self.bot.mk.LEGISLATURE_LEGISLATOR_NAME} "
                f"and voting starts for a Legislative Session."
            )

        await ctx.send(message)

    @dmsettings.command(name="legsubmit")
    async def legsubmit(self, ctx):
        """Toggle DMs for when someone submits a Bill or Motion"""

        new_value = await self.toggle_dm_setting(ctx.author.id, "leg_session_submit")

        if new_value:
            message = (
                f"{config.YES} You will now receive DMs when you are a member of the "
                f"{self.bot.mk.LEGISLATURE_CABINET_NAME} "
                f"and someone submits a Bill or Motion. "
                f"Note that you will never get a DM when a member of the "
                f"{self.bot.mk.LEGISLATURE_CABINET_NAME} is the one submitting."
            )
        else:
            message = (
                f"{config.YES} You will no longer receive DMs when you are a member of the "
                f"{self.bot.mk.LEGISLATURE_CABINET_NAME} and someone submits a Bill or Motion."
            )

        await ctx.send(message)

    @dmsettings.command(name="legwithdraw")
    async def legwithdraw(self, ctx):
        """Toggle DMs for when someone withdraws a Bill or Motion"""

        new_value = await self.toggle_dm_setting(ctx.author.id, "leg_session_withdraw")

        if new_value:
            message = (
                f"{config.YES} You will now receive DMs when you are a member of the "
                f"{self.bot.mk.LEGISLATURE_CABINET_NAME} and someone withdraws their Bill or Motion. "
                f"Note that you will never get a DM when a member of the "
                f"{self.bot.mk.LEGISLATURE_CABINET_NAME} is the one withdrawing."
            )

        else:
            message = (
                f"{config.YES} You will no longer receive DMs when you are a member of the "
                f"{self.bot.mk.LEGISLATURE_CABINET_NAME} and someone withdraws their Bill or Motion."
            )

        await ctx.send(message)

    @dmsettings.command(name="party")
    async def party_join_leave(self, ctx):
        """Toggle DMs for when someone joins or leaves your political party"""

        new_value = await self.toggle_dm_setting(ctx.author.id, "party_join_leave")

        if new_value:
            message = (
                f"{config.YES} You will now receive DMs when someone joins or leaves your political party."
            )

        else:
            message = (
                f"{config.YES} You will no longer receive DMs when someone joins or leaves your political party."
            )

        await ctx.send(message)


def setup(bot):
    bot.add_cog(Profile(bot))
