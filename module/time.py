from datetime import datetime
from discord.ext import commands
from config import config, token


class Time(commands.Cog):
    """Get the current time in various timezones"""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(name='time', case_insensitive=True, invoke_without_command=True)
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def time(self, ctx, zone: str):
        """Displays the current time of a specified timezone"""

        # If input is an abbreviation (UTC, EST etc.), make it uppercase for the TimeZoneDB request to work
        if len(zone) <= 5:
            zone = zone.upper()

        if token.TIMEZONEDB_API_KEY == "":
            await ctx.send(":x: Invalid TimeZoneDB API key.")
            return

        query_base = f"https://api.timezonedb.com/v2.1/get-time-zone?key={token.TIMEZONEDB_API_KEY}&format=json&" \
                     f"by=zone&zone={zone}"

        async with ctx.typing():
            async with self.bot.session.get(query_base) as response:
                time_response = await response.json()

            if time_response['status'] != "OK":
                return await ctx.send(f":x: '{zone}' is not a valid time zone!")

            us_time = datetime.utcfromtimestamp(time_response['timestamp']).strftime("%A, %B %d %Y "
                                                                                     " %I:%M:%S %p")
            eu_time = datetime.utcfromtimestamp(time_response['timestamp']).strftime("%A, %B %d %Y"
                                                                                     " %H:%M:%S")

            if zone.lower() == "utc":
                title = f"Current Time in UTC"
            else:
                title = f"Current Time in {time_response['abbreviation']}"

            embed = self.bot.embeds.embed_builder(title=title,
                                                  description="[See this list for available time zones.]"
                                                              "(https://timezonedb.com/time-zones)")
            embed.add_field(name="24-Hour Clock", value=eu_time, inline=False)
            embed.add_field(name="12-Hour Clock", value=us_time, inline=False)

            await ctx.send(embed=embed)

    @time.command(name='convert')
    async def convert(self, ctx):

        embed = self.bot.embeds.embed_builder(title=f"Convert between Time Zones",
                                              description="[This website is good for converting time across different "
                                                          "time zones.](https://www.worldtimebuddy.com/)")

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Time(bot))
