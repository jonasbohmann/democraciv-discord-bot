from discord.ext import commands


class SupremeCourt(commands.Cog, name="Supreme Court"):

    def __init__(self, bot):
        self.bot = bot


def setup(bot):
    bot.add_cog(SupremeCourt(bot))
