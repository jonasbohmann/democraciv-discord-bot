import uuid

from util import stv
from config import config
from discord.ext import commands


class Elections(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="stv")
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def stv(self, ctx, seats: int, quota: int):
        """Calculate election results of a given .csv file with STV

        Usage:
            Upload a .csv file and add the command as a comment to it like this:
            `-stv <seats> <quota>`, with the quota parameter being "0" for Hare and "1" for Droop
        """

        if quota not in range(0, 2):
            await ctx.send(f":x: Invalid quota, type '0' for Hare and '1' for Droop!")
            return

        try:
            csv = ctx.message.attachments[0]
        except IndexError:
            await ctx.send(f":x: You have to upload a .csv file to use this command!")
            return

        if not csv.filename.endswith('.csv'):
            await ctx.send(f":x: You have to upload a valid .csv file to use this command!")
            return

        _filename = f"{uuid.uuid4()}.csv"

        async with ctx.typing():
            await csv.save(f'db/{_filename}')

            try:
                output = await self.bot.loop.run_in_executor(None, stv.main, seats, _filename, quota)
            except Exception:
                output = None

            if output is None or output == "":
                results = "There was an error while calculating the results."
            else:
                results = output

            embed = self.bot.embeds.embed_builder(title=f"STV Results for {csv.filename}",
                                                  description=f"```glsl\n{results}```", time_stamp=True)
            await ctx.send(embed=embed)

    @stv.error
    async def stverror(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'seats':
                await ctx.send(':x: You have to specify the amount of available seats!\n\n**Usage**:\n'
                               'Upload a .csv file and add the command as a comment to it like this:'
                               ' `-stv <seats> <quota>`, with the quota parameter being "0" for Hare and "1" for Droop')

            if error.param.name == 'quota':
                await ctx.send(':x: You have to specify the quota!\n\n**Usage**:\n'
                               'Upload a .csv file and add the command as a comment to it like this:'
                               ' `-stv <seats> <quota>`, with the quota parameter being "0" for Hare and "1" for Droop')

        elif isinstance(error, commands.BadArgument):
            await ctx.send(':x: Error!\n\n**Usage**:\n'
                           'Upload a .csv file and add the command as a comment to it like this:'
                           ' `-stv <seats> <quota>`, with the quota parameter being "0" for Hare and "1" for Droop')


def setup(bot):
    bot.add_cog(Elections(bot))
