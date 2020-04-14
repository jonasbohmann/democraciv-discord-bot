import os
import uuid

from util import stv
from config import config
from discord.ext import commands


class Elections(commands.Cog, name="Election"):
    """Calculate election results with various methods."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="stv")
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def stv(self, ctx, seats: int, quota: str):
        """Calculate election results with STV

        **Usage:**
            Upload a .csv file and add the command as a comment to it like this:
            `-stv <seats> <quota>`, with the quota parameter being "hare" for Hare and "droop" for Droop
        """

        if quota.lower() == "hare":
            quota = 0

        elif quota.lower() == "droop":
            quota = 1

        else:
            return await ctx.send(f":x: Invalid quota, write 'hare' for Hare and 'droop' for Droop.")

        try:
            csv = ctx.message.attachments[0]
        except IndexError:
            await ctx.send(f":x: You have to upload a .csv file to use this command.")
            return

        if not csv.filename.endswith('.csv'):
            await ctx.send(f":x: You have to upload a valid .csv file for this command to work.")
            return

        _filename = f"{uuid.uuid4()}.csv"

        async with ctx.typing():
            # Check if stv dir exists
            if not os.path.isdir('./db/stv'):
                os.mkdir('./db/stv')

            await csv.save(f'db/stv/{_filename}')

            error = None

            try:
                output = await self.bot.loop.run_in_executor(None, stv.main, seats, _filename, quota)
            except Exception as e:
                output = None
                error = e

            if output is None or output == "":
                if error:
                    results = f"There was an error while calculating the results.\n\n\nError\n{error}"
                else:
                    results = "There was an error while calculating the results."

            else:
                results = output

            embed = self.bot.embeds.embed_builder(title=f"STV Results for {csv.filename}",
                                                  description=f"```glsl\n{results}```", footer=f"ID: {_filename}")
            await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Elections(bot))
