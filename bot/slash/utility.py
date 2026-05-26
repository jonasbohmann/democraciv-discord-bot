import io
import random

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import config
from bot.presenters import utility as utility_presenter
from bot.services.utility import UtilityService
from bot.slash import context as slash_context
from bot.slash import ui
from bot.utils import text


class UtilitySlash(commands.Cog):
    random_group = app_commands.Group(
        name="random",
        description="Random generators.",
    )

    def __init__(self, bot):
        self.bot = bot
        self.service = UtilityService(bot)

    @app_commands.command(
        name="delete-press-post",
        description="Delete a Reddit press post created by the bot.",
    )
    async def delete_press_post(self, interaction: discord.Interaction, url: str):
        ctx = slash_context.from_interaction(
            interaction,
            command_name="delete-press-post",
        )
        await ctx.defer()
        if (
            f"reddit.com/r/{config.DEMOCRACIV_SUBREDDIT.lower()}" not in url.lower()
            and "comments" not in url.lower()
        ):
            return await ctx.send(
                f"{config.NO} Make sure the link to your Reddit press post is in the exact Reddit comments format.",
                ephemeral=True,
            )

        partitioned_url = url.partition("reddit.com/r/")
        if not partitioned_url[2]:
            return await ctx.send(
                f"{config.NO} Make sure the link to your Reddit press post is in the exact Reddit comments format.",
                ephemeral=True,
            )

        url = f"https://oauth.reddit.com/r/{partitioned_url[2]}"
        error_msg = f"{config.NO} Something went wrong. Are you sure that you gave me a real link to a press Reddit post?"
        js = await self.bot.api_request("POST", "reddit/post/get", json={"url": url})

        try:
            post = js[0]["data"]["children"][0]["data"]
            if post["author"].lower() == "[deleted]":
                return await ctx.send(f"{config.HINT} This post was already removed.")

            if (
                post["subreddit"].lower() != config.DEMOCRACIV_SUBREDDIT.lower()
                or post["author"].lower() != config.STARBOARD_REDDIT_USERNAME.lower()
            ):
                return await ctx.send(error_msg, ephemeral=True)

            content = "".join(post["selftext"].split())
            post_id = post["name"]
        except (TypeError, KeyError, IndexError):
            return await ctx.send(error_msg, ephemeral=True)

        if f"!A_ID:{ctx.author.id}" not in content:
            return await ctx.send(
                f"{config.NO} You are not the author of that press article.",
                ephemeral=True,
            )

        resp = await self.bot.api_request(
            "POST",
            "reddit/post/delete",
            json={"id": post_id},
        )
        if "error" in resp:
            return await ctx.send(error_msg, ephemeral=True)

        await ctx.send(f"{config.YES} Your press article was removed from Reddit.")

    @app_commands.command(
        name="whois", description="Show detailed information about a member."
    )
    @app_commands.guild_only()
    async def whois(
        self, interaction: discord.Interaction, member: discord.Member = None
    ):
        ctx = slash_context.from_interaction(interaction, command_name="whois")
        await ctx.defer()
        member = member or ctx.author

        result = await self.service.get_whois(ctx, member)
        embed = utility_presenter.build_whois_embed(result)
        await ctx.send(embed=embed)

    @app_commands.command(name="avatar", description="View someone's avatar.")
    @app_commands.guild_only()
    async def avatar(self, interaction: discord.Interaction, user: discord.User = None):
        ctx = slash_context.from_interaction(interaction, command_name="avatar")
        await ctx.defer()
        user = user or ctx.author
        avatar_png = user.display_avatar.with_size(4096).url
        await ui.send_static(
            ctx,
            title=str(user),
            media_urls=[avatar_png],
            links=[ui.LayoutLink("Open Avatar", avatar_png, "\U0001f5bc")],
        )

    @app_commands.command(
        name="veterans", description="List the first 15 members who joined this server."
    )
    @app_commands.guild_only()
    async def veterans(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="veterans")
        await ctx.defer()

        result = await self.service.get_veterans(ctx)
        embed = utility_presenter.build_veterans_embed(result)
        await ctx.send(embed=embed)

    @app_commands.command(
        name="whohas", description="Show detailed information about a role."
    )
    @app_commands.guild_only()
    async def whohas(self, interaction: discord.Interaction, role: discord.Role):
        ctx = slash_context.from_interaction(interaction, command_name="whohas")
        await ctx.defer()
        result = self.service.get_role_info(ctx, role)
        embed = utility_presenter.build_role_info_embed(result)
        await ctx.send(embed=embed)

    @random_group.command(name="number", description="Generate a random number.")
    async def random_number(
        self,
        interaction: discord.Interaction,
        start: int = 1,
        end: int = 100,
    ):
        ctx = slash_context.from_interaction(interaction, command_name="random number")
        await ctx.defer()
        try:
            result = random.randint(start, end)
        except ValueError:
            return await ctx.send(
                f"{config.NO} Invalid random number range.", ephemeral=True
            )

        await ctx.send(
            f":arrows_counterclockwise: Random number ({start} - {end}): **{result}**"
        )

    @random_group.command(
        name="choose", description="Choose one option from a comma-separated list."
    )
    async def random_choose(self, interaction: discord.Interaction, choices: str):
        ctx = slash_context.from_interaction(interaction, command_name="random choose")
        await ctx.defer()
        parsed = [
            choice.strip()
            for choice in choices.replace("\n", ",").split(",")
            if choice.strip()
        ]
        if not parsed:
            return await ctx.send(
                f"{config.NO} Give me at least one choice.", ephemeral=True
            )

        await ctx.send(f":tada: The winner is: **{random.choice(parsed)}**")

    @random_group.command(name="coin", description="Flip a coin.")
    async def random_coin(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="random coin")
        await ctx.send(
            f":arrows_counterclockwise: **{random.choice(['Heads', 'Tails'])}**"
        )

    @app_commands.command(name="vibecheck", description="Run a vibe check.")
    @app_commands.guild_only()
    async def vibecheck(
        self, interaction: discord.Interaction, user: discord.User = None
    ):
        ctx = slash_context.from_interaction(interaction, command_name="vibecheck")
        await ctx.defer()
        user = user or ctx.author

        not_vibing = [
            "https://i.kym-cdn.com/entries/icons/mobile/000/031/163/Screen_Shot_2019-09-16_at_10.22.26_AM.jpg",
            "https://s3.amazonaws.com/media.thecrimson.com/photos/2019/11/18/194724_1341037.png",
            "https://i.kym-cdn.com/photos/images/newsfeed/001/574/493/3ab.jpg",
            "https://i.imgflip.com/3ebtvt.jpg",
            "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcT814jrNuqJsaVVHGqWw_0snlcysLN5fLpocEYrx6hzkgXYx7RV5w&s",
            "https://img.buzzfeed.com/buzzfeed-static/static/2019-10/7/15/asset/c5dd65974640/sub-buzz-521-1570462442-1.png?downsize=700:*&output-format=auto&output-quality=auto",
            "https://images-wixmp-ed30a86b8c4ca887773594c2.wixmp.com/f/12132fe4-1709-4287-9dcc-4ee9fc252a01/ddk55pz-bf72cab3-2b9e-474e-94a8-00e5f53d2baf.jpg?token=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1cm46YXBwOjdlMGQxODg5ODIyNjQzNzNhNWYwZDQxNWVhMGQyNmUwIiwiaXNzIjoidXJuOmFwcDo3ZTBkMTg4OTgyMjY0MzczYTVmMGQ0MTVlYTBkMjZlMCIsIm9iaiI6W1t7InBhdGgiOiJcL2ZcLzEyMTMyZmU0LTE3MDktNDI4Ny05ZGNjLTRlZTlmYzI1MmEwMVwvZGRrNTVwei1iZjcyY2FiMy0yYjllLTQ3NGUtOTRhOC0wMGU1ZjUzZDJiYWYuanBnIn1dXSwiYXVkIjpbInVybjpzZXJ2aWNlOmZpbGUuZG93bmxvYWQiXX0.Sb6Axu0O6iZ3YmZJHg5wRe-r41iLnWVqa_ddWrtbQlo",
            "https://pbs.twimg.com/media/EHgYHjOX4AAuv6s.jpg",
            "https://pbs.twimg.com/media/EGTsxzaUwAAuBLG?format=jpg&name=900x900",
            "https://66.media.tumblr.com/c2fc65d9f8614dbd9bb7378983e0598e/tumblr_pxw332rEmZ1yom1s3o1_1280.png",
        ]

        vibing = [
            "https://preview.redd.it/i-will-give-your-ocs-a-vibe-check-v0-0y5skb0tx9sb1.jpeg?width=750&format=pjpg&auto=webp&s=b1d8598547a600f7c589a069ee92be6a08bb1589",
            "https://images.squarespace-cdn.com/content/63c88a61bbbb6e3e419189da/1687420314895-70N8D0I60O36DB4PCRX0/You-Passed-The-Vibe-Check-Cats-y2k-png-design.jpg?format=1500w&content-type=image%2Fjpeg",
            "https://i.kym-cdn.com/photos/images/original/001/599/028/bf3.jpg",
            "https://i.redd.it/p4e6a65i3bw31.jpg",
            "https://media.makeameme.org/created/congratulations-you-have-61e05e0d4b.jpg",
        ]

        passed = random.randrange(1, stop=100) >= 65

        if passed:
            image = random.choice(vibing)
            pretty = "passed"
        else:
            image = random.choice(not_vibing)
            pretty = "not passed"

        embed = text.SafeEmbed(
            title=f"{user} has __{pretty}__ the vibe check",
        )
        embed.set_image(url=image)
        await ctx.send(embed=embed)

    @app_commands.command(name="dog", description="Show a random dog image or video.")
    async def dog(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="dog")
        await ctx.defer()
        async with self.bot.session.get("https://random.dog/woof") as resp:
            if resp.status != 200:
                return await ctx.send(f"{config.NO} No dog found :(")

            filename = await resp.text()
            url = f"https://random.dog/{filename}"

        filesize = ctx.guild.filesize_limit if ctx.guild else 8388608
        if filename.endswith((".mp4", ".webm")):
            async with self.bot.session.get(url) as other:
                if other.status != 200:
                    return await ctx.send(
                        f"{config.NO} Could not download dog video :("
                    )
                if int(other.headers["Content-Length"]) >= filesize:
                    return await ctx.send(
                        f"{config.NO} Video was too big to upload, watch it here instead: {url}"
                    )

                fp = io.BytesIO(await other.read())
                return await ctx.send(file=discord.File(fp, filename=filename))

        embed = text.SafeEmbed(title="Random Dog")
        embed.set_image(url=url)
        embed.set_footer(text="Just for Taylor.")
        await ctx.send(embed=embed)

    @app_commands.command(name="cat", description="Show a random cat.")
    async def cat(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="cat")
        await ctx.defer()
        async with self.bot.session.get(
            "https://api.thecatapi.com/v1/images/search"
        ) as response:
            if response.status != 200:
                return await ctx.send(f"{config.NO} No cat found :(")

            data = await response.json()

        await ui.send_static(ctx, title="Random Cat", media_urls=[data[0]["url"]])

    @app_commands.command(
        name="server-invite", description="Create a permanent invite for this server."
    )
    @app_commands.guild_only()
    async def server_invite(self, interaction: discord.Interaction):
        ctx = slash_context.from_interaction(interaction, command_name="server-invite")
        await ctx.defer()
        invite = await ctx.channel.create_invite(max_age=0, unique=False)
        await ctx.send(invite.url)


async def setup(bot):
    await bot.add_cog(UtilitySlash(bot))
