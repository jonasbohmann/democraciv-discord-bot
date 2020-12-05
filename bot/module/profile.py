import collections

from discord.ext import commands, menus

from bot.config import config
from bot.utils import context, text


class EditDMSettingsMenu(menus.Menu):
    def __init__(self, settings):
        super().__init__(timeout=120.0, delete_message_after=True)
        self.settings = settings
        self._make_result()

    def _make_result(self):
        self.result = collections.namedtuple("EditDMSettingsMenuResult", ["confirmed", "result"])
        self.result.confirmed = False

        self.result.result = {"mute_kick_ban": self.settings["ban_kick_mute"],
                              "leg_session_open": self.settings["leg_session_open"],
                              "leg_session_update": self.settings["leg_session_update"],
                              "leg_session_submit": self.settings["leg_session_submit"],
                              "leg_session_withdraw": self.settings["leg_session_withdraw"],
                              "party_join_leave": self.settings["party_join_leave"]}

        return self.result

    def _make_embed(self):
        embed = text.SafeEmbed(
            description=f"You can toggle each notification on and off. Once you're done, hit {config.YES} to confirm, or {config.NO} to cancel.\n\n"
            f":one:  -  {self.emojify_settings(self.result.result['mute_kick_ban'])} DM when you get muted, kicked or banned\n"
                        f":two:  -  {self.emojify_settings(self.result.result['leg_session_open'])} *({self.bot.mk.LEGISLATURE_LEGISLATOR_NAME} Only)* DM when a {self.bot.mk.LEGISLATURE_ADJECTIVE} Session opens\n"
                        f":three:  -  {self.emojify_settings(self.result.result['leg_session_update'])} *({self.bot.mk.LEGISLATURE_LEGISLATOR_NAME} Only)* DM when voting starts for a {self.bot.mk.LEGISLATURE_ADJECTIVE} Session\n"
                        f":four:  -  {self.emojify_settings(self.result.result['leg_session_submit'])} "
                        f"*({self.bot.mk.LEGISLATURE_CABINET_NAME} Only)* DM when "
                        f"someone submits a Bill or Motion\n"
                        f":five:  -  {self.emojify_settings(self.result.result['leg_session_withdraw'])} "
                        f"*({self.bot.mk.LEGISLATURE_CABINET_NAME} Only)* DM when "
                        f"someone withdraws a Bill or Motion\n"
                        f":six:  -  {self.emojify_settings(self.result.result['party_join_leave'])} *(Party Leaders Only)* DM when someone joins or leaves your political party\n"
        )
        embed.set_author(name=self.ctx.author, icon_url=self.ctx.author_icon)
        return embed

    async def send_initial_message(self, ctx, channel):
        return await ctx.send(embed=self._make_embed())

    @menus.button("1\N{variation selector-16}\N{combining enclosing keycap}")
    async def first(self, payload):
        self.result.result["mute_kick_ban"] = not self.result.result["mute_kick_ban"]
        await self.message.edit(embed=self._make_embed())

    @menus.button("2\N{variation selector-16}\N{combining enclosing keycap}")
    async def snd(self, payload):
        self.result.result["leg_session_open"] = not self.result.result["leg_session_open"]
        await self.message.edit(embed=self._make_embed())

    @menus.button("3\N{variation selector-16}\N{combining enclosing keycap}")
    async def thrd(self, payload):
        self.result.result["leg_session_update"] = not self.result.result["leg_session_update"]
        await self.message.edit(embed=self._make_embed())

    @menus.button("4\N{variation selector-16}\N{combining enclosing keycap}")
    async def fourth(self, payload):
        self.result.result["leg_session_submit"] = not self.result.result["leg_session_submit"]
        await self.message.edit(embed=self._make_embed())

    @menus.button("5\N{variation selector-16}\N{combining enclosing keycap}")
    async def fifth(self, payload):
        self.result.result["leg_session_withdraw"] = not self.result.result["leg_session_withdraw"]
        await self.message.edit(embed=self._make_embed())

    @menus.button("6\N{variation selector-16}\N{combining enclosing keycap}")
    async def sixth(self, payload):
        self.result.result["party_join_leave"] = not self.result.result["party_join_leave"]
        await self.message.edit(embed=self._make_embed())

    @menus.button(config.YES)
    async def confirm(self, payload):
        self.result.confirmed = True
        self.stop()

    @menus.button(config.NO)
    async def cancel(self, payload):
        self._make_result()
        self.stop()

    async def prompt(self, ctx):
        self.emojify_settings = ctx.bot.get_cog("Server").emojify_settings
        await self.start(ctx, wait=True)
        return self.result


class Profile(context.CustomCog):
    """Manage personal settings"""

    async def ensure_dm_settings(self, user: int):
        settings = await self.bot.db.fetchrow("SELECT * FROM dm_setting WHERE user_id = $1", user)

        if not settings:
            settings = await self.bot.db.fetchrow("INSERT INTO dm_setting (user_id) VALUES ($1) RETURNING *", user)

        return settings

    @commands.group(
        name="dms",
        aliases=["dm", "pm", "dmsettings", "dm-settings", "dmsetting"],
        case_insensitive=True,
        invoke_without_command=True,
    )
    async def dmsettings(self, ctx):
        """Manage your DM notifications from me"""
        settings = await self.ensure_dm_settings(ctx.author.id)
        result = await EditDMSettingsMenu(settings).prompt(ctx)

        await self.bot.db.execute("UPDATE dm_setting SET ban_kick_mute = $1, leg_session_open = $2, "
                                  "leg_session_update = $3, leg_session_submit = $4, "
                                  "leg_session_withdraw = $5, party_join_leave = $6 WHERE user_id = $7",
                                  *result.result.values(), ctx.author.id)

        await ctx.send(f"{config.YES} Your settings were updated.")


def setup(bot):
    bot.add_cog(Profile(bot))
