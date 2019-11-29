import config
import random

from discord.ext import commands


class Random(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='random')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    async def random(self, ctx, *arg):
        """Returns a random number or choice

            Usage:
            -random
                Random number between 1-100
            -random coin
                Heads or Tails
            -random 6
                Random number between 1-6
            -random choice England Rome
                Random choice between "England" and "Rome"
            """

        if not arg:
            start = 1
            end = 100
        elif arg[0] == 'flip' or arg[0] == 'coin':
            coin = ['Heads', 'Tails']
            await ctx.send(f':arrows_counterclockwise: {random.choice(coin)}')
            return

        elif arg[0] == 'choice':
            choices = list(arg)
            choices.pop(0)
            await ctx.send(f':tada: The winner is: {random.choice(choices)}')
            return

        elif len(arg) == 1:
            start = 1
            end = int(arg[0])
        else:
            start = 1
            end = 100

        await ctx.send(
            f'**:arrows_counterclockwise:** Random number ({start} - {end}): {random.randint(start, end)}')


def setup(bot):
    bot.add_cog(Random(bot))
