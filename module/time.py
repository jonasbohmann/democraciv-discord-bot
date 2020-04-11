from datetime import datetime
from discord.ext import commands
from config import config, token


class Time(commands.Cog):
    """Get the current time in various timezones. Shows both 12 and 24-hour formatting."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='time', aliases=['clock, tz'])
    @commands.cooldown(1, config.BOT_COMMAND_COOLDOWN, commands.BucketType.user)
    async def time(self, ctx, *, zone: str):
        """Displays the current time of a specified timezone"""

        # If input is an abbreviation (UTC, EST etc.), make it uppercase for the TimeZoneDB request to work
        if len(zone) <= 5:
            zone = zone.upper()

        if not token.TIMEZONEDB_API_KEY:
            return await ctx.send(":x: Invalid TimeZoneDB API key.")

        query_base = f"https://api.timezonedb.com/v2.1/get-time-zone?key={token.TIMEZONEDB_API_KEY}&format=json&" \
                     f"by=zone&zone={zone}"

        async with ctx.typing():
            async with self.bot.session.get(query_base) as response:
                if response.status == 200:
                    time_response = await response.json()

            if time_response['status'] != "OK":
                return await ctx.send(f":x: `{zone}` is not a valid time zone or area code. "
                                      f"See the list of available time zones here: "
                                      f"<https://timezonedb.com/time-zones>")

            date = datetime.utcfromtimestamp(time_response['timestamp']).strftime("%A, %B %d %Y")
            us_time = datetime.utcfromtimestamp(time_response['timestamp']).strftime("%I:%M:%S %p")
            eu_time = datetime.utcfromtimestamp(time_response['timestamp']).strftime("%H:%M:%S")

            if zone.lower() == "utc":
                title = f":clock1:  Current Time in UTC"
            else:
                title = f":clock1:  Current Time in {time_response['abbreviation']}"

            embed = self.bot.embeds.embed_builder(title=title, description="")
            embed.add_field(name="Date", value=date, inline=False)
            embed.add_field(name="Time (12-Hour Clock)", value=us_time, inline=False)
            embed.add_field(name="Time (24-Hour Clock)", value=eu_time, inline=False)
            embed.set_footer(text="See 'timezonedb.com/time-zones' for a list of available time zones.")
            await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Time(bot))
