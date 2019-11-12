import config
import discord
import datetime

import mechanize as mechanize
from discord.ext import commands
from util.embed import embed_builder


class Legislature(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='submit')
    @commands.cooldown(1, config.getCooldown(), commands.BucketType.user)
    @commands.has_any_role("Legislator", "Legislature")  # TODO - Have bot check what the exact leg role is named
    async def submit(self, ctx, google_docs_url: str):
        """Submit a new bill directly to the current Speaker of the Legislature.

        Usage:
        -----
        -submit [Google Docs Link of Bil]
        """
        speaker_role = discord.utils.get(ctx.guild.roles, name="Speaker of the Legislature")

        if len(google_docs_url) <= 10 or not google_docs_url:
            await ctx.send(":x: You have to give me a valid Google Docs URL of the bill you want to submit!")
            return

        if ".google.com" not in google_docs_url:
            await ctx.send(":x: That doesn't look like a Google Docs URL.")
            return

        if speaker_role is None:
            await ctx.send(":x: Couldn't find the Speaker role.")
            return

        if len(speaker_role.members) == 0:
            await ctx.send(":x: No one has the Speaker role.")
            return

        speaker_person = speaker_role.members[0]  # Assuming there's only 1 speaker ever

        try:
            browser = mechanize.Browser()
            browser.open(google_docs_url)
            bill_title = browser.title()
        except Exception:
            await ctx.send(":x: Unexpected error occurred. Try again!")
            return

        embed = embed_builder(title="New Bill Submitted", description="")
        embed.add_field(name="Title", value=bill_title, inline=False)
        embed.add_field(name="Author", value=ctx.message.author.name)
        embed.add_field(name="Time of Submission (UTC)", value=datetime.datetime.utcnow())
        embed.add_field(name="URL", value=google_docs_url, inline=False)

        try:
            await speaker_person.create_dm()
            await speaker_person.dm_channel.send(embed=embed)
        except Exception:
            await ctx.send(":x: Unexpected error occurred.")
            return

        await ctx.send(f":white_check_mark: Successfully submitted '{bill_title}' to the Speaker of the Legislature!")


def setup(bot):
    bot.add_cog(Legislature(bot))
