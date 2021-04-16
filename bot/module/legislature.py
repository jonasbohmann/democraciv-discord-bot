import asyncio
import collections
import datetime
import asyncpg
import discord
import typing
import re

from discord.ext import commands
from discord.ext.commands import Greedy

from bot.config import config, mk
from bot.utils import models, text, paginator, context, mixin, checks, converter, exceptions
from bot.utils.models import Bill, Session, Motion, SessionStatus


class PassScheduler(text.RedditAnnouncementScheduler):

    def get_reddit_post_title(self) -> str:
        session = self._objects[0].session
        return f"Passed Bills from {self.bot.mk.LEGISLATURE_ADJECTIVE} Session #{session.id}"

    def get_reddit_post_content(self) -> str:
        content = [f"The following bills were passed into law by {self.bot.mk.LEGISLATURE_NAME}."
                   f"\n\n###Relevant Links\n\n"
                   f"* [Constitution]({self.bot.mk.CONSTITUTION})\n"
                   f"* [Legal Code]({self.bot.mk.LEGAL_CODE}) or write `-laws` in #bot on our "
                   f"[Discord Server](https://discord.gg/AK7dYMG)\n"
                   f"* [Docket/Worksheet]({self.bot.mk.LEGISLATURE_DOCKET})\n\n---\n  &nbsp; \n\n"]

        for bill in self._objects:
            submitter = bill.submitter or context.MockUser()
            content.append(f"__**Law #{bill.id} - [{bill.name}]({bill.link})**__\n\n*Written by "
                           f"{submitter.display_name} ({submitter})*"
                           f"\n\n{bill.description}\n\n &nbsp;")

        outro = f"""\n\n &nbsp; \n\n---\n\nAll these bills are now active laws and have to be followed. 
                \n\n\n\n*I am a [bot](https://github.com/jonasbohmann/democraciv-discord-bot/) 
                and this is an automated service. Contact u/Jovanos (DerJonas#8036 on Discord) for further questions 
                or bug reports.*"""

        content.append(outro)
        return "\n\n".join(content)

    def get_message(self) -> str:
        message = [f"The following bills were **passed into law** by {self.bot.mk.LEGISLATURE_NAME}.\n"]

        for obj in self._objects:
            message.append(f"Bill #{obj.id} - **{obj.name}** (<{obj.tiny_link}>)")
            # if obj.is_vetoable:
            #    message.append(f"-  **{obj.name}** (<{obj.tiny_link}>)")
            # else:
            #    message.append(f"-  __**{obj.name}**__ (<{obj.tiny_link}>)")

        p = config.BOT_PREFIX
        # message.append(
        #    f"\nAll non veto-able bills are now laws (marked as __underlined__) and can be found in `{p}laws`, "
        #    f"as well with `{p}laws search`. The others were sent to the {self.bot.mk.MINISTRY_NAME} "
        #    f"(`{p}{self.bot.mk.MINISTRY_COMMAND} bills`) to either pass "
        #    f"(`{p}{self.bot.mk.MINISTRY_COMMAND} pass`) or veto (`{p}{self.bot.mk.MINISTRY_COMMAND} veto`) them."
        # )

        message.append(f"\nAll these bills are now laws and can be found in `{p}laws`, as well with `{p}laws search`.")
        return "\n".join(message)


class OverrideScheduler(text.AnnouncementScheduler):
    def get_message(self) -> str:
        message = [
            f"The {self.bot.mk.MINISTRY_NAME}'s **veto of the following bills were overridden** "
            f"by the {self.bot.mk.LEGISLATURE_NAME}.\n"
        ]

        for obj in self._objects:
            message.append(f"Bill #{obj.id} - **{obj.name}** (<{obj.tiny_link}>)")

        message.append(
            f"\nAll of the above bills are now law and can be found in `{config.BOT_PREFIX}laws`, "
            f"as well with `{config.BOT_PREFIX}laws search`."
        )

        return "\n".join(message)


LEG_COMMAND_ALIASES = ["leg", "legislature"] if mk.MarkConfig.LEGISLATURE_COMMAND.lower() != "legislature" else ["leg"]


class Legislature(context.CustomCog, mixin.GovernmentMixin, name=mk.MarkConfig.LEGISLATURE_NAME):
    """Allows the Government to organize legislative sessions and bill & motion submissions"""

    def __init__(self, bot):
        super().__init__(bot)
        self.email_regex = re.compile(r"[^@]+@[^@]+\.[^@]+")
        self.pass_scheduler = PassScheduler(bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL,
                                            subreddit=config.DEMOCRACIV_SUBREDDIT)
        self.override_scheduler = OverrideScheduler(bot, mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL)

        if not self.bot.mk.LEGISLATURE_MOTIONS_EXIST:
            self.bot.get_command(self.bot.mk.LEGISLATURE_COMMAND).remove_command("motion")
            self.bot.get_command(f"{self.bot.mk.LEGISLATURE_COMMAND} withdraw").remove_command("motion")

    @commands.command(name="bill", aliases=["bills", "b"], hidden=True)
    async def _bill(self, ctx: context.CustomContext):
        """This only exists to serve as an alias to `{PREFIX}{LEGISLATURE_COMMAND} bill`"""
        ctx.message.content = ctx.message.content.replace(f"{ctx.prefix}{ctx.invoked_with}",
                                                          f"{ctx.prefix}{self.bot.mk.LEGISLATURE_COMMAND.lower()} "
                                                          f"{ctx.invoked_with}")
        new_ctx = await self.bot.get_context(ctx.message)
        return await self.bot.invoke(new_ctx)

    @commands.command(name="motion", aliases=["motions", "m"], hidden=True)
    async def _motion(self, ctx: context.CustomContext):
        """This only exists to serve as an alias to `{PREFIX}{LEGISLATURE_COMMAND} motion`"""
        ctx.message.content = ctx.message.content.replace(f"{ctx.prefix}{ctx.invoked_with}",
                                                          f"{ctx.prefix}{self.bot.mk.LEGISLATURE_COMMAND.lower()} "
                                                          f"{ctx.invoked_with}")
        new_ctx = await self.bot.get_context(ctx.message)
        return await self.bot.invoke(new_ctx)

    @commands.group(
        name=mk.MarkConfig.LEGISLATURE_COMMAND.lower(),
        aliases=LEG_COMMAND_ALIASES,
        case_insensitive=True,
        invoke_without_command=True,
    )
    async def legislature(self, ctx):
        """Dashboard for {LEGISLATURE_LEGISLATOR_NAME_PLURAL} with important links and the status of the current session"""

        active_leg_session = await self.get_active_leg_session()

        if active_leg_session is None:
            current_session_value = "There currently is no open session."
        else:
            current_session_value = f"Session #{active_leg_session.id} - {active_leg_session.status.value}"

        embed = text.SafeEmbed()
        embed.set_author(
            icon_url=self.bot.mk.NATION_ICON_URL,
            name=f"The {self.bot.mk.LEGISLATURE_NAME} of {self.bot.mk.NATION_FULL_NAME}",
        )
        speaker_value = []

        if isinstance(self.speaker, discord.Member):
            speaker_value.append(f"{self.bot.mk.speaker_term}: {self.speaker.mention}")
        else:
            speaker_value.append(f"{self.bot.mk.speaker_term}: -")

        if isinstance(self.vice_speaker, discord.Member):
            speaker_value.append(f"{self.bot.mk.vice_speaker_term}: {self.vice_speaker.mention}")
        else:
            speaker_value.append(f"{self.bot.mk.vice_speaker_term}: -")

        embed.add_field(name=self.bot.mk.LEGISLATURE_CABINET_NAME, value="\n".join(speaker_value))
        embed.add_field(
            name="Links",
            value=f"[Constitution]({self.bot.mk.CONSTITUTION})\n[Legal Code]({self.bot.mk.LEGAL_CODE})"
                  f"\n[Docket/Worksheet]({self.bot.mk.LEGISLATURE_DOCKET})",
            inline=True,
        )
        embed.add_field(name="Current Session", value=current_session_value, inline=False)
        await ctx.send(embed=embed)

    @legislature.group(
        name="bill",
        aliases=["b", "bills"],
        case_insensitive=True,
        invoke_without_command=True,
    )
    async def bill(self, ctx: context.CustomContext, *, bill_id: models.FuzzyBill = None):
        """List all bills or get details about a single bill"""

        if bill_id is None:
            return await self._paginate_all_(ctx, model=models.Bill)

        return await self._detail_view(ctx, obj=bill_id)

    @bill.command(name="synchronize", aliases=["sync", "refresh"])
    @checks.has_any_democraciv_role(mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER)
    async def b_refresh(self, ctx, bills: commands.Greedy[models.Bill]):
        """Synchronize the name & content of one or multiple bills with Google Docs"

        This gets the current title and the current content of the Google Docs document of a bill,
         and saves that to my database. In case my search commands show outdated text of a bill,
         or I show the wrong name of a bill, use this command to fix that.

        **Example**
            `{PREFIX}{COMMAND} 12`
            `{PREFIX}{COMMAND} 45 46 49 51 52`"""
        errs = []

        for bill in bills:
            name, keywords, content = await bill.fetch_name_and_keywords()

            if not name:
                errs.append(f"Error syncing Bill #{bill.id} - {bill.name}. Skipping update..")
                continue

            await self.bot.db.execute("UPDATE bill SET name = $1, content = $3 WHERE id = $2", name, bill.id, content)
            await self.bot.db.execute("DELETE FROM bill_lookup_tag WHERE bill_id = $1", bill.id)
            await self.bot.api_request("POST", "bill/update", json={"id": bill.id})

            id_with_kws = [(bill.id, keyword) for keyword in keywords]
            self.bot.loop.create_task(
                self.bot.db.executemany(
                    "INSERT INTO bill_lookup_tag (bill_id, tag) VALUES " "($1, $2) ON CONFLICT DO NOTHING ", id_with_kws
                )
            )

        msg = f"{config.YES} Synchronized {len(bills) - len(errs)}/{len(bills)} bills with Google Docs."

        if errs:
            fmt = "\n".join(errs)
            msg = f"{fmt}\n\n{msg}"

        await ctx.send(msg)

    @bill.command(name="edit", aliases=["update", "e"])
    @checks.is_democraciv_guild()
    async def b_edit(self, ctx, *, bill_id: models.Bill):
        """Edit the Google Docs link or summary of a bill

        **Example**
            `{PREFIX}{COMMAND} 16`
        """
        bill = bill_id

        if not self.is_cabinet(ctx.author) or bill._submitter != ctx.author.id:
            return await ctx.send(f"{config.NO} Only the {self.bot.mk.speaker_term} and the original "
                                  f"submitter of a bill can edit it.")

        menu = text.EditModelMenu(choices_with_formatted_explanation={"link": "Google Docs Link",
                                                                      "description": "Short Summary"},
                                  title=f"{config.USER_INTERACTION_REQUIRED}  What about {bill.name} (#{bill.id}) do "
                                        f"you want to change?")

        result = await menu.prompt(ctx)

        if not result.confirmed:
            return await ctx.send(f"{config.NO} You didn't decide on what to edit.")

        to_change = result.choices

        if True not in to_change.values():
            return await ctx.send(f"{config.NO} You didn't decide on what to edit.")

        if to_change["link"]:
            if not self.is_cabinet(ctx.author) and bill.session.status is not SessionStatus.SUBMISSION_PERIOD:
                return await ctx.send(f"{config.NO} You can only change the link to your bill if the "
                                      f"session it was submitted in is still in Submission Period.\n{config.HINT} "
                                      f"However, the {self.bot.mk.speaker_term} can change the link of any bill at "
                                      f"any given time.")

            link = await ctx.input(
                f"{config.USER_INTERACTION_REQUIRED} Reply with the new Google Docs link to the bill."

            )

            if not self.is_google_doc_link(link):
                link = bill.link
                tiny_link = bill.tiny_link
                await ctx.send(f"{config.NO} That doesn't look like a Google Docs URL. "
                               f"The link to the bill will not be changed.")

            else:
                tiny_link = await self.bot.tinyurl(link)

        else:
            link = bill.link
            tiny_link = bill.tiny_link

        if to_change["description"]:
            description = await ctx.input(
                f"{config.USER_INTERACTION_REQUIRED} Reply with a new **short** summary of what the bill does.",
                timeout=400,
            )
            if not description:
                description = "*No summary provided by submitter.*"

        else:
            description = bill.description

        are_you_sure = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to edit `{bill.name}` (#{bill.id})?"
        )

        if not are_you_sure:
            return await ctx.send("Cancelled.")

        changed_bill = models.Bill(bot=self.bot, link=link, submitter_description=description)
        name, keywords, content = await changed_bill.fetch_name_and_keywords()

        if not name or not content:
            return await ctx.send(f"{config.NO} Something went wrong with Google Docs. "
                                  f"The bill was not edited, try again later.")

        await self.bot.db.execute(
            "UPDATE bill SET name = $1, content = $2, submitter_description = $3, link = $4, tiny_link = $5 "
            "WHERE id = $6", name, content, description, link, tiny_link, bill.id)

        await self.bot.db.execute("DELETE FROM bill_lookup_tag WHERE bill_id = $1", bill.id)
        await self.bot.api_request("POST", "bill/update", silent=True, json={"id": bill.id})

        id_with_kws = [(bill.id, keyword) for keyword in keywords]
        self.bot.loop.create_task(
            self.bot.db.executemany(
                "INSERT INTO bill_lookup_tag (bill_id, tag) VALUES ($1, $2) ON CONFLICT DO NOTHING ", id_with_kws
            )
        )

        await ctx.send(f"{config.YES} Bill #{bill.id} `{bill.name}` was updated.")

    @bill.command(name="history", aliases=["h"])
    async def b_history(self, ctx: context.CustomContext, *, bill_id: models.Bill):
        """See when a bill was first introduced, passed into Law, repealed, etc."""
        fmt_history = [
            f"**{entry.date.strftime('%d %B %Y')}** - {entry.after}   "
            f"({entry.after.emojified_status(verbose=False)})"
            for entry in bill_id.history
        ]
        fmt_history.insert(0, "All dates are in UTC.\n")

        pages = paginator.SimplePages(
            entries=fmt_history, title=f"{bill_id.name} (#{bill_id.id})", title_url=bill_id.link
        )
        await pages.start(ctx)

    @bill.command(name="search", aliases=["s"])
    async def b_search(self, ctx: context.CustomContext, *, query: str):
        """Search for a bill"""
        return await self._search_model(ctx, model=models.Bill, query=query)

    @bill.command(name="from", aliases=["f", "by"])
    async def b_from(
            self,
            ctx: context.CustomContext,
            *,
            member_or_party: typing.Union[
                converter.CaseInsensitiveMember,
                converter.CaseInsensitiveUser,
                converter.PoliticalParty,
                converter.FuzzyCIMember,
            ] = None,
    ):
        """List all bills that a specific person or Political Party submitted"""
        return await self._from_person_model(ctx, member_or_party=member_or_party, model=models.Bill)

    @legislature.group(
        name="motion",
        aliases=["m", "motions"],
        case_insensitive=True,
        invoke_without_command=True,
    )
    async def motion(self, ctx: context.CustomContext, *, motion_id: models.FuzzyMotion = None):
        """List all motions or get details about a single motion"""

        if motion_id is None:
            return await self._paginate_all_(ctx, model=models.Motion)

        return await self._detail_view(ctx, obj=motion_id)

    @motion.command(name="edit", aliases=["update", "e"])
    @checks.is_democraciv_guild()
    async def m_edit(self, ctx, *, motion_id: models.Motion):
        """Edit the title or content of a motion

        **Example**
            `{PREFIX}{COMMAND} 16`
        """
        motion = motion_id

        if not self.is_cabinet(ctx.author):
            if motion._submitter != ctx.author.id:
                return await ctx.send(f"{config.NO} Only the {self.bot.mk.speaker_term} and the original "
                                      f"submitter of a motion can edit it.")

            if motion.session.status is not SessionStatus.SUBMISSION_PERIOD:
                return await ctx.send(f"{config.NO} You can only edit your motion if the "
                                      f"session it was submitted in is still in Submission Period.\n{config.HINT} "
                                      f"However, the {self.bot.mk.speaker_term} can edit your motion at "
                                      f"any given time.")

        menu = text.EditModelMenu(choices_with_formatted_explanation={"title": "Title",
                                                                      "content": "Content"},
                                  title=f"{config.USER_INTERACTION_REQUIRED}  What about {motion.name} (#{motion.id}) "
                                        f"do you want to change?")

        result = await menu.prompt(ctx)

        if not result.confirmed:
            return await ctx.send(f"{config.NO} You didn't decide on what to edit.")

        to_change = result.choices

        if True not in to_change.values():
            return await ctx.send(f"{config.NO} You didn't decide on what to edit.")

        if to_change["title"]:
            title = await ctx.input(
                f"{config.USER_INTERACTION_REQUIRED} Reply with the new short **title** for the motion."
            )

        else:
            title = motion.title

        if to_change["content"]:
            content = await ctx.input(
                f"{config.USER_INTERACTION_REQUIRED} Reply with the new **content** of the motion. If the motion is"
                " inside a Google Docs document, just use a link to that for this."
            )

            paste = await self.bot.make_paste(content)

            if not paste:
                return await ctx.send(
                    f"{config.NO} The motion will not be updated, there was a problem with <https://mystb.in>. "
                    "Sorry, try again in a few minutes."
                )
        else:
            content = motion.description
            paste = motion._link

        are_you_sure = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want to edit `{motion.name}` (#{motion.id})?"
        )

        if not are_you_sure:
            return await ctx.send("Cancelled.")

        await self.bot.db.execute(
            "UPDATE motion SET title = $1, description = $2, paste_link = $3 WHERE id = $4",
            title, content, paste, motion.id)

        await ctx.send(f"{config.YES} Motion #{motion.id} `{motion.name}` was updated.")

    @motion.command(name="from", aliases=["f", "by"])
    async def m_from(
            self,
            ctx: context.CustomContext,
            *,
            member_or_party: typing.Union[
                converter.CaseInsensitiveMember,
                converter.CaseInsensitiveUser,
                converter.PoliticalParty,
                converter.FuzzyCIMember,
            ] = None,
    ):
        """List all motions that a specific person or Political Party submitted"""
        return await self._from_person_model(ctx, model=models.Motion, member_or_party=member_or_party)

    @motion.command(name="search", aliases=["s"])
    async def m_search(self, ctx: context.CustomContext, *, query: str):
        """Search for a motion"""
        return await self._search_model(ctx, model=models.Motion, query=query)

    @legislature.group(
        name="session",
        aliases=["s"],
        case_insensitive=True,
        invoke_without_command=True,
    )
    async def leg_session(self, ctx: context.CustomContext, session: Session = None):
        """Get details about a session from the Legislature

        **Usage**
        `{PREFIX}{COMMAND}` to see details about the last session
        `{PREFIX}{COMMAND} <number>` to see details about a specific session"""

        # User invoked -legislature session without arguments
        if session is None:
            session = await self.get_last_leg_session()

            if session is None:
                return await ctx.send(f"{config.NO} There hasn't been a session yet.\n{config.HINT} The "
                                      f"{self.bot.mk.speaker_term} can open one at any time with "
                                      f"`{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} session open`.")

        if len(session.bills) > 0:
            pretty_bills = []

            for bill_id in session.bills:
                bill = await Bill.convert(ctx, bill_id)
                if bill.status.is_law:
                    pretty_bills.append(f"__Bill #{bill.id}__ - [{bill.short_name}]({bill.tiny_link})")
                else:
                    pretty_bills.append(f"Bill #{bill.id} - [{bill.short_name}]({bill.tiny_link})")
        else:
            pretty_bills = ["-"]

        embed = text.SafeEmbed()
        embed.set_author(icon_url=self.bot.mk.NATION_ICON_URL, name=f"Legislative Session #{session.id}")

        if session.speaker is not None:
            embed.add_field(name="Opened by", value=session.speaker.mention)
        else:
            embed.add_field(name="Opened by", value="*Person left Democraciv*")

        embed.add_field(name="Status", value=session.status.value, inline=True)
        embed.add_field(name="Date", value=self.format_session_times(session), inline=False)

        if session.vote_form:
            embed.add_field(name="Vote Form", value=f"[Link]({session.vote_form})", inline=False)

        if self.bot.mk.LEGISLATURE_MOTIONS_EXIST:
            if len(session.motions) > 0:
                pretty_motions = []
                for motion_id in session.motions:
                    motion = await Motion.convert(ctx, motion_id)
                    pretty_motions.append(f"Motion #{motion.id} - [{motion.short_name}]({motion.link})")
            else:
                pretty_motions = ["-"]

            pretty_motions = "\n".join(pretty_motions)
            too_long = (
                f"This text was too long for Discord, so I put it on "
                f"[here.]({await self.bot.make_paste(pretty_motions)})"
            )
            embed.add_field(
                name="Submitted Motions",
                value=pretty_motions,
                inline=False,
                too_long_value=too_long,
            )

        pretty_bills = "\n".join(pretty_bills)
        too_long_ = (
            f"This text was too long for Discord, so I put it on [here.]({await self.bot.make_paste(pretty_bills)})"
        )
        embed.add_field(
            name="Submitted Bills",
            value=pretty_bills,
            inline=False,
            too_long_value=too_long_,
        )

        embed.set_footer(text="Bills that are underlined are active laws. All times are in UTC.")
        await ctx.send(embed=embed)

    @leg_session.command(name="open", aliases=["o"])
    @checks.has_any_democraciv_role(mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER)
    async def opensession(self, ctx):
        """Opens a session for the submission period to begin"""

        active_leg_session = await self.get_active_leg_session()

        if active_leg_session is not None:
            return await ctx.send(
                f"{config.NO} There is still an open session, close session #{active_leg_session.id} "
                f"first with `{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} session close`."
            )

        new_session = await self.bot.db.fetchval(
            "INSERT INTO legislature_session (speaker, opened_on) VALUES ($1, $2) RETURNING id",
            ctx.author.id,
            datetime.datetime.utcnow(),
        )

        p = config.BOT_PREFIX
        l = self.bot.mk.LEGISLATURE_COMMAND
        info = text.SafeEmbed(
            title=f"{config.HINT}  Help | Government System:  Legislative Sessions",
            description=f"Once you feel like enough time has passed for people to "
                        f"submit their bills and motions, you can lock submissions by doing either "
                        f"one of these options:\n\n1. If you want to stop submissions coming in, but aren't ready "
                        f"yet to start voting, you can **lock the session** with `{p}{l} session lock`. You "
                        f"can allow submissions to be submitted again by unlocking the session with "
                        f"`{p}{l} session unlock`.\n\n2.  "
                        f"*(Optional)* Set the session into *Voting Period* with "
                        f"`{p}{l} session vote`. The only advantage of setting a session into Voting "
                        f"Period before directly closing it, is that I will DM every legislator "
                        f"a reminder to vote and the link to the voting form, and the voting form "
                        f"will be displayed in `{p}{l} session`. After enough time has passed for "
                        f"everyone to vote, you would close the session as described in the "
                        f"next step.\n\n"
                        f"3. Close the session entirely with "
                        f"`{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} session close`.",
        )

        info.add_field(
            name="Optional: Voting Form",
            value="If you want to use Google Forms to vote, "
                  "I can generate that Google Form for you and fill "
                  f"it with all the bills and motions that were submitted. "
                  f"Take a look at `{p}{l} session export form`. You can use my generated Google Form "
                  f"for the `{p}{l} session vote` command.",
            inline=False,
        )

        info.add_field(
            name="Bill & Motion Submissions",
            value=f"As {self.bot.mk.speaker_term}, you can remove any bill or "
                  f"motion from this session with `{p}{l} withdraw`. Everyone else can use that command "
                  f"too, but they're only allowed to withdraw the bills/motions that they "
                  f"themselves also submitted.",
            inline=False,
        )

        info.add_field(
            name="Failed Bills from previous Sessions",
            value="Are there any bills from last session that "
                  f"failed, that you want to give a second chance in this session? Don't bother "
                  f"doing `{p}{l} submit` all over again, instead use `{p}{l} resubmit <bill_ids>` to "
                  f"move any old, failed bills to this session.",
            inline=False,
        )

        await ctx.send(
            f"{config.YES} The **submission period** for session #{new_session} was opened, and bills & "
            f"motions can now be submitted."
        )

        self.bot.loop.create_task(ctx.send_with_timed_delete(embed=info))

        await self.gov_announcements_channel.send(
            f"The **submission period** for {self.bot.mk.LEGISLATURE_ADJECTIVE} Session "
            f"#{new_session} has started! Bills and motions can be "
            f"submitted with `{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} submit`."
        )

        await self.dm_legislators(
            reason="leg_session_open",
            message=f":envelope_with_arrow: The **submission period** for {self.bot.mk.LEGISLATURE_ADJECTIVE} Session "
                    f" #{new_session} has started! Submit your bills and motions with "
                    f"`{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} submit` on the {self.bot.dciv.name} server."
        )

    @leg_session.command(name="lock")
    @checks.has_any_democraciv_role(mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER)
    async def locksession(self, ctx):
        """Lock (deny) submissions for the currently active session"""

        active_leg_session = await self.get_active_leg_session()
        p = config.BOT_PREFIX
        l = self.bot.mk.LEGISLATURE_COMMAND

        if active_leg_session is None:
            return await ctx.send(
                f"{config.NO} There is no open session.\n{config.HINT} You can open a new session "
                f"at any time with `{p}{l} session open`."
            )

        if active_leg_session.status is not SessionStatus.SUBMISSION_PERIOD:
            return await ctx.send(f"{config.NO} You can only lock sessions that are in Submission Period.")

        await self.bot.db.execute("UPDATE legislature_session SET status = $1 WHERE id = $2",
                                  SessionStatus.LOCKED.value,
                                  active_leg_session.id)

        await self.gov_announcements_channel.send(
            f"The Speaker has locked submissions for {self.bot.mk.LEGISLATURE_ADJECTIVE} "
            f"Session #{active_leg_session.id}. Nothing can be submitted until the Speaker decides "
            f"to unlock the session again."
        )

        await ctx.send(f"{config.YES} Submissions for {self.bot.mk.LEGISLATURE_ADJECTIVE} "
                       f"Session #{active_leg_session.id} have been locked.\n{config.HINT} Want to allow "
                       f"submissions again? Unlock the session with `{p}{l} session unlock`.\n"
                       f"{config.HINT} In case you intend to leave submissions locked until voting starts "
                       f"in order to use this time as a **debate period**, you can make me post the current list "
                       f"of submission to **r/{config.DEMOCRACIV_SUBREDDIT}** with `{p}{l} session export reddit`. "
                       f"That reddit post may help with more focused debates & feedback on bills & motions.")

    @leg_session.command(name="unlock")
    @checks.has_any_democraciv_role(mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER)
    async def unlocksession(self, ctx):
        """Unlock (allow) submissions for the currently active session again"""

        active_leg_session = await self.get_active_leg_session()
        p = config.BOT_PREFIX
        l = self.bot.mk.LEGISLATURE_COMMAND

        if active_leg_session is None:
            return await ctx.send(
                f"{config.NO} There is no open session.\n{config.HINT} You can open a new session "
                f"at any time with `{p}{l} session open`."
            )

        if active_leg_session.status is not SessionStatus.LOCKED:
            return await ctx.send(f"{config.NO} You can only unlock sessions that are already locked.")

        await self.bot.db.execute("UPDATE legislature_session SET status = $1 WHERE id = $2",
                                  SessionStatus.SUBMISSION_PERIOD.value,
                                  active_leg_session.id)

        await self.gov_announcements_channel.send(
            f"The Speaker has unlocked submissions for {self.bot.mk.LEGISLATURE_ADJECTIVE} "
            f"Session #{active_leg_session.id}, meaning you can now submit bills & motions with "
            f"`{p}{l} submit` again."
        )

        await ctx.send(f"{config.YES} Submissions for {self.bot.mk.LEGISLATURE_ADJECTIVE} "
                       f"Session #{active_leg_session.id} have been unlocked.")

    @leg_session.command(name="vote", aliases=["u", "v", "update"])
    @checks.has_any_democraciv_role(mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER)
    async def updatesession(self, ctx: context.CustomContext):
        """Changes the current session's status to be open for voting"""

        active_leg_session = await self.get_active_leg_session()
        p = config.BOT_PREFIX
        l = self.bot.mk.LEGISLATURE_COMMAND

        if active_leg_session is None:
            return await ctx.send(
                f"{config.NO} There is no open session.\n{config.HINT} You can open a new session "
                f"at any time with `{p}{l} session open`."
            )

        if active_leg_session.status is SessionStatus.VOTING_PERIOD:
            return await ctx.send(f"{config.NO} This session is already in the Voting Period.")

        voting_form = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the link to this session's Google Forms voting "
            f"form.\n{config.HINT} Reply with gibberish if you want me to generate that form for you."
        )

        if not self.is_google_doc_link(voting_form):
            return await ctx.send(f"{config.HINT} Use the "
                                  f"`{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} session export form` "
                                  f"command to make me generate the form for you, then use this command "
                                  f"again once you're all set.")

        await active_leg_session.start_voting(voting_form)

        await ctx.send(
            f"{config.YES} Session #{active_leg_session.id} is now in **voting period**.\n{config.HINT} You can make "
            f"me post the list of bill & motion submissions to **r/{config.DEMOCRACIV_SUBREDDIT}** with "
            f"`{p}{l} session export reddit`.\n{config.HINT} Once you feel "
            f"like enough time has passed for people to vote, close this session with `{p}{l} session close`. "
            f"I'll go over what happens after that once you close the session."
        )

        await self.gov_announcements_channel.send(
            f"The **voting period** for {self.bot.mk.LEGISLATURE_ADJECTIVE} "
            f"Session #{active_leg_session.id} "
            f"has started!\n{self.bot.mk.LEGISLATURE_LEGISLATOR_NAME_PLURAL} can vote here: <{voting_form}>"
        )

        await self.dm_legislators(
            reason="leg_session_update",
            message=f":ballot_box: The **voting period** for {self.bot.mk.LEGISLATURE_ADJECTIVE} Session "
                    f"#{active_leg_session.id} has started!\nVote here: {voting_form}",
        )

    @leg_session.command(name="close", aliases=["c"])
    @checks.has_any_democraciv_role(mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER)
    async def closesession(self, ctx):
        """Closes the current session"""

        active_leg_session = await self.get_active_leg_session()

        p = config.BOT_PREFIX
        l = self.bot.mk.LEGISLATURE_COMMAND

        if active_leg_session is None:
            return await ctx.send(
                f"{config.NO} There is no open session.\n{config.HINT} You can open a new "
                f"session with `{p}{l} session open` at any time."
            )

        await active_leg_session.close()

        #  Update all bills that did not pass
        await self.bot.db.execute(
            "UPDATE bill SET status = $1 WHERE leg_session = $2",
            models.BillFailedLegislature.flag.value,
            active_leg_session.id,
        )

        info = text.SafeEmbed(
            title=f"{config.HINT}  Help | Government System:  Legislative Sessions",
            description=f"Now, tally the results and tell me which bills passed with "
                        f"`{p}{l} pass <bill_ids>`.\n\nYou do not have to tell me which bills "
                        f"failed in the vote, I will "
                        f"automatically set every bill from this session that you do not "
                        f"explicitly pass with `{p}{l} pass <bill_ids>` as failed.",
        )

        info.add_field(
            name="Why can't I pass motions?",
            value="Motions are intended for short-term, temporary actions that do not "
                  f"require to be kept as record in `{p}laws`. As such, they lack some features that bills "
                  f"have, "
                  "such as passing them into law.\n\nAn example for a use case for motions could be a "
                  "'Motion to recall Person XY' motion, because if that motion to recall passes, "
                  "why would we need to keep that motion as a record on our Legal Code, it's a "
                  "one-and-done thing.",
            inline=False,
        )

        info.add_field(
            name="Updating the Legal Code",
            value=f"As {self.bot.mk.speaker_term}, one of your obligations is "
                  f"probably to make sure our Legal Code is up-to-date. "
                  f"While my `{p}laws` command is an always up-to-date legal code, some people might "
                  f"prefer one as an old-fashioned document.\n\nYou can use my `{p}laws export` command to "
                  f"make me generate that for you! Just give me the link to a Google Docs document "
                  f"and I will make that an up-to-date Legal Code.",
            inline=False,
        )

        # info.add_field(
        #    name="'Help! Someone submitted a bill as not veto-able but it's not' or vice-versa",
        #    value="Don't worry, while there isn't a command (yet) for you to fix that, "
        #          f"you can just ping {self.bot.owner.mention} to fix this.",
        #    inline=False,
        # )

        info.add_field(
            name="Keep it rolling",
            value=f"Now that you've closed the last session, you can keep your "
                  f"{self.bot.mk.LEGISLATURE_LEGISLATOR_NAME_PLURAL} busy by opening the next session "
                  f"with `{p}{l} session open` right away. It doesn't matter how long the "
                  f"Submission Period is, and it doesn't hurt anyone that they can submit bills "
                  f"around the clock.\n\nJust sit back, let submissions come in and once you're ready to "
                  f"'start' the session 'for real', tell your {self.bot.mk.LEGISLATURE_LEGISLATOR_NAME_PLURAL} that "
                  f"submissions will be locked soon, and schedule a few debates. Now that everyone already "
                  f"had days to write and submit their bills, more time is left for debate, discussion and "
                  f"collective brainstorming once the session really 'starts'.",
        )

        await ctx.send(f"{config.YES} Session #{active_leg_session.id} was closed.")

        self.bot.loop.create_task(ctx.send_with_timed_delete(embed=info))

        await self.gov_announcements_channel.send(
            f"{self.bot.mk.LEGISLATURE_ADJECTIVE} Session #{active_leg_session.id} has been **closed** by the "
            f"{self.bot.mk.LEGISLATURE_CABINET_NAME}."
        )

    @leg_session.group(name="export", aliases=["es", "ex", "e"], hidden=True,
                       case_insensitive=True, invoke_without_command=True)
    async def export(self, ctx: context.CustomContext):
        """Automate the most time consuming Speaker responsibilities with these commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send(f"{config.NO} You have to tell me how you would like this session to be exported.")
            await ctx.send_help(ctx.command)

    @export.command(name="spreadsheet", aliases=['sheet', 'sheets', 's'])
    async def export_spreadsheet(self, ctx, session: Session = None):
        """Export a session's submissions into copy & paste-able formatting for Google Spreadsheets"""

        session = session or await self.get_last_leg_session()

        if session is None:
            return await ctx.send(f"{config.NO} There hasn't been a session yet.")

        async with ctx.typing():
            bills = [await Bill.convert(ctx, bill_id) for bill_id in session.bills]
            motions = [await Motion.convert(ctx, motion_id) for motion_id in session.motions]

            b_ids = [f"Bill #{bill.id} ({len(bill.sponsors)} sponsors)" for bill in bills]
            b_hyperlinks = [f'=HYPERLINK("{bill.link}"; "{bill.name}")' for bill in bills]
            m_ids = [f"Motion #{motion.id}" for motion in motions]
            m_hyperlinks = [f'=HYPERLINK("{motion.link}"; "{motion.name}")' for motion in motions]

            exported = [
                f"Export of {self.bot.mk.LEGISLATURE_ADJECTIVE} Session {session.id} -- {datetime.datetime.utcnow().strftime('%c')}\n\n\n",
                f"Xth Session - {session.opened_on.strftime('%B %d %Y')} (Bot Session {session.id})\n\n"
                "----- Submitted Bills -----\n",
            ]

            exported.extend(b_ids)
            exported.append("\n")
            exported.extend(b_hyperlinks)
            exported.append("\n\n----- Submitted Motions -----\n")
            exported.extend(m_ids)
            exported.append("\n")
            exported.extend(m_hyperlinks)

            spreadsheet_formatting_link = await self.bot.make_paste("\n".join(exported))

        await ctx.send(f"__**Spreadsheet Export of {self.bot.mk.LEGISLATURE_ADJECTIVE} Session #{session.id}**__\n"
                       f"This session's bills and motions were exported into a format that "
                       f"you can easily copy & paste into Google Spreadsheets, for example for a "
                       f"Legislative Docket: **<{spreadsheet_formatting_link}>**\n\nSee the video below to see how to "
                       f"speed up your Speaker duties with this.\n"
                       f"https://cdn.discordapp.com/attachments/709411002482950184/709412385034862662/howtoexport.mp4")

    @export.command(name="form", aliases=['forms', 'voting', 'f'])
    @commands.cooldown(1, 120, commands.BucketType.user)
    async def export_form(self, ctx, session: Session = None):
        """Generate the Google Forms voting form with all the submitted bills & motions for a session"""

        session = session or await self.get_last_leg_session()

        if session is None:
            return await ctx.send(f"{config.NO} There hasn't been a session yet.")

        form_url = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} Reply with an **edit** link to an **empty** Google Forms "
            f"form you created. I will then fill that form to make it the voting form.\n{config.HINT} "
            "*Create a new Google Form here: <https://forms.new>, then click on the three dots in the upper right, "
            "then on 'Add collaborators', after which a new window should pop up. "
            "Click on 'Change' on the bottom left, and change the link from 'Restricted' to the other option. "
            "Then copy the link and send it here.*",
            delete_after=True,
            timeout=400,
        )

        if not form_url:
            ctx.command.reset_cooldown(ctx)
            return

        if not self.is_google_doc_link(form_url):
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(f"{config.NO} That doesn't look like a Google Forms URL. This process was cancelled.")

        min_sponsors = await ctx.input(f"{config.USER_INTERACTION_REQUIRED} Reply with the minimum amount of "
                                       f"sponsors a bill needs to be included on the "
                                       f"Voting Form.\n{config.HINT} If you "
                                       f"reply with `0`, every bill will be included, "
                                       f"regardless the amount of sponsors it has."
                                       f"\n{config.HINT} Motions don't have a lot of the features that bills have. "
                                       f"Motions cannot be sponsored, so all motions will be on the form.")

        try:
            min_sponsors = int(min_sponsors)
        except ValueError:
            return await ctx.send(f"{config.NO} You didn't reply with a number.")

        generating = await ctx.send(
            f"{config.YES} I will generate the voting form for {self.bot.mk.LEGISLATURE_ADJECTIVE} "
            f"Session #{session.id}. \n:arrows_counterclockwise: This may take a few minutes..."
        )

        def safe_get_submitter(thing) -> str:
            return thing.submitter.display_name if thing.submitter else "*Unknown Person*"

        async with ctx.typing():
            bills = [await Bill.convert(ctx, bill_id) for bill_id in session.bills]
            motions = [await Motion.convert(ctx, motion_id) for motion_id in session.motions]

            bills = list(filter(lambda b: len(b.sponsors) >= min_sponsors, bills))

            bills_info = {f"{b.name} (#{b.id})": f"Submitted by {safe_get_submitter(b)} with "
                                                 f"{len(b.sponsors)} sponsor(s)\n"
                                                 f"{b.link}\n\n{b.description}"
                          for b in bills}

            motions_info = {f"{m.name} (#{m.id})": f"Submitted by {safe_get_submitter(m)}\n{m.link}"
                            for m in motions}

            result = await self.bot.run_apps_script(
                script_id="MME1GytLY6YguX02rrXqPiGqnXKElby-M",
                function="generate_form",
                parameters=[form_url, session.id, bills_info, motions_info],
            )

        embed = text.SafeEmbed(
            title=f"Export of {self.bot.mk.LEGISLATURE_ADJECTIVE} Session #{session.id}",
            description="Make sure to double check the form to make sure it's "
                        "correct.\n\nNote that you may have to adjust "
                        "the form to comply with this nation's laws as this comes with no guarantees of a form's valid "
                        "legal status.\n\n:warning: Remember to change the edit link you "
                        f"gave me earlier to be **'Restricted'** again.",
        )

        embed.add_field(
            name="Voting Form",
            value=f"Link: {result['response']['result']['view']}\n\n"
                  f"Shortened: {result['response']['result']['short-view']}",
            inline=False,
        )

        await ctx.send(f"{config.HINT} You can use this voting form to start the Voting Period of a session with "
                       f"`{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} session vote`.", embed=embed)
        self.bot.loop.create_task(generating.delete())

    @export.command(name="reddit")
    @checks.has_any_democraciv_role(mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER)
    async def export_reddit(self, ctx):
        """Make me post an overview of the current session and its submissions to our subreddit """

        session = await self.get_active_leg_session()

        if session is None:
            return await ctx.send(f"{config.NO} There is no open session in either Submission Period or "
                                  f"Voting Period right now.")

        bills = [await Bill.convert(ctx, i) for i in session.bills]
        motions = [await Motion.convert(ctx, i) for i in session.motions]

        speaker = session.speaker or context.MockUser()
        cntnt = []

        intro = (f"Speaker {speaker.display_name} ({speaker}) opened the Submission Period for this session on "
                 f"{session.opened_on.strftime('%B %d, %Y at %H:%M')} UTC. ")

        if session.voting_started_on:
            intro += f"Voting started on {session.voting_started_on.strftime('%B %d, %Y at %H:%M')} UTC " \
                     f"[on this form]({session.vote_form}). "

        intro += f"\n\nFeel free to use this thread to debate and propose feedback on bills & motions, " \
                 f"in case voting has not started yet.\n\n###Relevant Links\n\n* " \
                 f"[Constitution]({self.bot.mk.CONSTITUTION})\n" \
                 f"* [Legal Code]({self.bot.mk.LEGAL_CODE}) or write `-laws` in #bot on our " \
                 f"[Discord Server](https://discord.gg/AK7dYMG)\n" \
                 f"* [Docket/Worksheet]({self.bot.mk.LEGISLATURE_DOCKET})\n\n  &nbsp; \n\n"

        cntnt.append(intro)

        if bills:
            cntnt.append("\n\n###Submitted Bills\n---\n &nbsp;")

        for bill in bills:
            submitter = bill.submitter or context.MockUser()
            cntnt.append(f"__**Bill #{bill.id} - [{bill.name}]({bill.link})**__\n\n*Submitted by "
                         f"{submitter.display_name} ({submitter}) with {len(bill.sponsors)} sponsor(s)*"
                         f"\n\n{bill.description}\n\n &nbsp;")

        if motions:
            cntnt.append("\n\n###Submitted Motions\n---\n &nbsp;")

        for motion in motions:
            submitter = motion.submitter or context.MockUser()
            cntnt.append(f"__**Motion #{motion.id} - [{motion.name}]({motion.link})**__\n\n*Submitted by "
                         f"{submitter.display_name} ({submitter})*"
                         f"\n\n{motion.description}\n\n &nbsp;")

        outro = f"""\n\n &nbsp; \n\n--- \n\n*I am a [bot](https://github.com/jonasbohmann/democraciv-discord-bot/) 
        and this is an automated service. Contact u/Jovanos (DerJonas#8036 on Discord) for further questions or bug 
        reports.*"""

        cntnt.append(outro)

        content = "\n\n".join(cntnt)

        js = {"subreddit": config.DEMOCRACIV_SUBREDDIT,
              "title": f"{self.bot.mk.LEGISLATURE_ADJECTIVE} Session #{session.id} - Docket & Submissions",
              "content": content}

        result = await self.bot.api_request("POST", "reddit/post", json=js)

        if "error" in result:
            raise exceptions.DemocracivBotAPIError()

        await ctx.send(f"{config.YES} A summary of session #{session.id} was posted "
                       f"to r/{config.DEMOCRACIV_SUBREDDIT}.")

    async def paginate_all_sessions(self, ctx):
        all_sessions = await self.bot.db.fetch("SELECT id, opened_on, closed_on FROM legislature_session ORDER BY id")
        pretty_sessions = []

        for record in all_sessions:
            opened_on = record["opened_on"].strftime("%B %d")

            if record["closed_on"]:
                closed_on = record["closed_on"].strftime("%B %d %Y")
                pretty_sessions.append(f"**Session #{record['id']}**  - {opened_on} to {closed_on}")
            else:
                pretty_sessions.append(f"**Session #{record['id']}**  - {opened_on}")

        pages = paginator.SimplePages(
            entries=pretty_sessions,
            icon=self.bot.mk.NATION_ICON_URL,
            author=f"All Sessions of the {self.bot.mk.NATION_ADJECTIVE} {self.bot.mk.LEGISLATURE_NAME}",
            empty_message="There hasn't been a session yet.",
        )
        await pages.start(ctx)

    @staticmethod
    def format_session_times(session: Session) -> str:
        formatted_time = [f"**Opened**: {session.opened_on.strftime('%A, %B %d %Y at %H:%M')}"]

        if session.voting_started_on:
            formatted_time.append(
                f"**Voting Started**: {session.voting_started_on.strftime('%A, %B %d %Y at %H:%M')}"
            )

        if session.closed_on:
            # Session is closed
            formatted_time.append(f"**Ended**: {session.closed_on.strftime('%A, %B %d %Y at %H:%M')}")

        return "\n".join(formatted_time)

    @leg_session.command(name="all", aliases=["a"])
    async def leg_session_all(self, ctx: context.CustomContext):
        """View a history of all previous sessions of the {LEGISLATURE_NAME}"""
        return await self.paginate_all_sessions(ctx)

    async def make_google_docs_bill(self, ctx) -> typing.Optional[str]:
        name = await ctx.input(
            f"{config.YES} I will make a Google Docs document for you instead.\n"
            f"{config.USER_INTERACTION_REQUIRED} Reply with the **name** of the bill you want to submit."
        )

        await ctx.send(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the **text** of your bill.\n\n"
            f"{config.HINT} You can reply with as many messages as you need for this. Once you're done, reply with "
            f"just the word `stop` and we will continue with the process."
        )

        messages = []
        start = datetime.datetime.utcnow()

        while True:
            try:
                _message = await self.bot.wait_for(
                    "message", check=lambda m: m.author == ctx.author and m.channel == ctx.channel, timeout=180
                )

                _ctx = await self.bot.get_context(_message)

                if _ctx.valid:
                    continue

                if _message.content.lower() == "stop":
                    break

                messages.append(_message)
                await ctx.send(f"{config.YES} That message was added to the text of your bill.\n{config.HINT} You can "
                               f"write more messages if you want. If not, reply with just the word `stop` to stop "
                               f"and continue with the submission process.\n"
                               f"{config.HINT} If you edit or delete any of your messages, I will also "
                               f"reflect that change in the text of your bill.")
            except asyncio.TimeoutError:
                if datetime.datetime.utcnow() - start >= datetime.timedelta(minutes=15):
                    break
                else:
                    continue

        if not messages:
            await ctx.send(f"{config.HINT} You didn't write any text for your bill. The bill submission "
                           f"process was cancelled.")
            return

        # check if messages were deleted
        messages = [discord.utils.get(self.bot.cached_messages, id=mes.id) for mes in messages]

        if not any(messages):
            await ctx.send(f"{config.HINT} You deleted all your messages. The bill submission process was cancelled.")
            return

        messages = list(filter(None, messages))

        email = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the **email address** "
            f"of your Google Account if you want me to transfer ownership of the document to you. "
            f"If not, just reply with gibberish.",
            delete_after=True,
        )

        if not self.email_regex.fullmatch(email):
            email = "No Email"

        author = f"{ctx.author.display_name} ({ctx.author})"

        bill_text = []

        for mes in messages:
            # get message again in case it was edited
            mes = discord.utils.get(self.bot.cached_messages, id=mes.id)

            # message was deleted
            if not mes:
                continue

            if mes.content:
                bill_text.append(mes.clean_content)

        bill_text = "\n\n".join(bill_text)

        async with ctx.typing():
            result = await self.bot.run_apps_script(
                script_id="M_fLh3UOUzLzW873Z7VZ1emqnXKElby-M",
                function="make_google_doc",
                parameters=[name, bill_text, email, author],
            )

            link = result["response"]["result"]["view"]
            fixed_link = link.replace("open?id=", "document/d/")
            fixed_link = f"{fixed_link}/edit"

        if "share_error" in result["response"]["result"]:
            await ctx.send(
                f"{config.NO} While generating the Google Doc for your bill was successful, there was an error while "
                f"setting the link of your Google Docs document to public. Unfortunately this error just sometimes "
                f"happens on Google's side, and there is nothing I can do to circumvent it. "
                f"Please set the link to public by yourself, or otherwise no one else can "
                f"view your bill: <{fixed_link}>"
            )

        return fixed_link

    async def submit_bill(
            self, ctx: context.CustomContext, current_leg_session_id: int
    ) -> typing.Optional[discord.Embed]:

        # Google Docs Link
        google_docs_url = await ctx.input(
            f"{config.YES} You will submit a **bill**.\n"
            f"{config.USER_INTERACTION_REQUIRED} Reply with the Google Docs link to the bill you want to submit.\n\n"
            f"{config.HINT} If you don't have your bill in a Google Docs document but instead just as text, "
            f"reply with gibberish to make me generate a Google Docs document for you."
        )

        if not self.is_google_doc_link(google_docs_url):
            google_docs_url = await self.make_google_docs_bill(ctx)

        if not google_docs_url:
            return

        is_vetoable = False

        # Vetoable
        # is_vetoable = await ctx.confirm(
        #   f"{config.USER_INTERACTION_REQUIRED} Is the {self.bot.mk.MINISTRY_NAME} legally allowed to vote on (veto) this bill?"
        # )

        bill_description = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} Reply with a **short** summary of what your bill does.",
            timeout=400,
        )

        if not bill_description:
            bill_description = "*No summary provided by submitter.*"

        async with ctx.typing():
            tiny_url = await self.bot.tinyurl(google_docs_url)

            if tiny_url is None:
                await ctx.send(
                    f"{config.NO} Your bill was not submitted since there was a problem with the URL shortening "
                    f"service. Sorry, try again in a few minutes."
                )
                return

            bill = models.Bill(bot=self.bot, link=google_docs_url, submitter_description=bill_description)
            name, tags, content = await bill.fetch_name_and_keywords()

            if not name:
                await ctx.send(f"{config.NO} Something went wrong. Are you sure you made your "
                               f"Google Docs document public for everyone to view?")
                return

            bill_id = await self.bot.db.fetchval(
                "INSERT INTO bill (leg_session, name, link, submitter, is_vetoable, "
                "submitter_description, tiny_link, content) VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id",
                current_leg_session_id,
                name,
                google_docs_url,
                ctx.author.id,
                is_vetoable,
                bill_description,
                tiny_url,
                content
            )

            bill.id = bill_id
            await bill.status.log_history(old_status=models.BillSubmitted.flag, new_status=models.BillSubmitted.flag)

            id_with_tags = [(bill_id, tag) for tag in tags]
            self.bot.loop.create_task(
                self.bot.db.executemany(
                    "INSERT INTO bill_lookup_tag (bill_id, tag) VALUES " "($1, $2) ON CONFLICT DO NOTHING ",
                    id_with_tags,
                )
            )

            embed = text.SafeEmbed(
                title="Bill Submitted",
                description="Hey! A new **bill** was just submitted.",
                timestamp=datetime.datetime.utcnow(),
            )
            embed.add_field(name="Title", value=name, inline=False)
            embed.add_field(name="Author", value=ctx.message.author.name, inline=False)
            embed.add_field(name="Session", value=current_leg_session_id)
            # embed.add_field(
            #    name=f"{self.bot.mk.MINISTRY_NAME} Veto Allowed",
            #    value="Yes" if is_vetoable else "No",
            # )
            embed.add_field(
                name="Time of Submission (UTC)",
                value=datetime.datetime.utcnow(),
                inline=False,
            )
            embed.add_field(name="URL", value=google_docs_url, inline=False)

        await self.bot.api_request("POST", "bill/add", silent=True, json={"id": bill_id})

        p = config.BOT_PREFIX
        l = self.bot.mk.LEGISLATURE_COMMAND
        info = text.SafeEmbed(
            title=f"{config.HINT}  Help | Government System:  Bill Submissions",
            description=f"The {self.bot.mk.speaker_term} has been informed about your " f"bill submission.",
        )

        info.add_field(
            name="Sponsors",
            value="Depending on current legislative procedures or laws, your bill might need a specific "
                  f"amount of sponsors before the Speaker allows a vote on it. "
                  f"Tell your supporters to sponsor your bill with `{p}{l} sponsor {bill_id}`. The list "
                  f"of sponsors will be displayed on your bill's detail page, `{p}{l} bill {bill_id}`.",
            inline=False,
        )

        info.add_field(
            name="I want to change something in my bill",
            value=f"During the Submission Period, you __do not__ have to withdraw your bill and submit it "
                  f"as a new bill again if you want to keep working on your bill and do some changes, "
                  f"based on feedback for example.\n\nUntil the Voting Period, just make your changes in "
                  f"the Google Docs document. It would be fair to your colleagues to inform them on any "
                  f"changes to your bill, though.\n\nDo __not__ edit your bill if the session is already in "
                  f"Voting Period and people are already voting on it, as a way to mislead them or "
                  f"to sneak anything secret in.",
            inline=False,
        )

        info.add_field(
            name="Withdrawing a Bill",
            value=f"If, for whatever reason, you want to withdraw your bill from this "
                  f"session, use the `{p}{l} withdraw bill {bill_id}` command.\n\n"
                  f"You can only withdraw your bills during the Submission Period of a legislative session, "
                  f"while the {self.bot.mk.speaker_term} can withdraw _every_ bill, at any time.",
            inline=False,
        )

        info.add_field(
            name="Additional Commands",
            value=f"Congratulations! Your submitted bill will now show up in the detail page "
                  f"for the current session `{p}{l} session`, in `{p}{l} bills`, "
                  f"`{p}{l} bills from {ctx.author.name}` and "
                  f"`{p}{l} bills from <your_party>` if you belong to a political party, and "
                  f"everyone can search for it based on matching keywords "
                  f"with `{p}{l} bill search <keyword>`.",
        )
        await ctx.send(
            f"{config.YES} Your bill `{name}` was submitted for session #{current_leg_session_id}.",
        )

        self.bot.loop.create_task(ctx.send_with_timed_delete(embed=info))
        return embed

    async def submit_motion(
            self, ctx: context.CustomContext, current_leg_session_id: int
    ) -> typing.Optional[discord.Embed]:

        title = await ctx.input(
            f"{config.YES} You will submit a **motion**.\n"
            f"{config.USER_INTERACTION_REQUIRED} Reply with a short **title** for your motion."
        )

        if not title:
            return

        description = await ctx.input(
            f"{config.USER_INTERACTION_REQUIRED} Reply with the **content** of your motion. If your motion is"
            " inside a Google Docs document, just use a link to that for this."
        )

        if not description:
            return

        async with ctx.typing():
            haste_bin_url = await self.bot.make_paste(description)

            if not haste_bin_url:
                await ctx.send(
                    f"{config.NO} Your motion was not submitted, there was a problem with <https://mystb.in>. "
                    "Sorry, try again in a few minutes."
                )
                return

            await self.bot.db.execute(
                "INSERT INTO motion (leg_session, title, description, submitter, paste_link) "
                "VALUES ($1, $2, $3, $4, $5)",
                current_leg_session_id,
                title,
                description,
                ctx.author.id,
                haste_bin_url,
            )

            embed = text.SafeEmbed(
                title="Motion Submitted",
                description="Hey! A new **motion** was just submitted.",
                timestamp=datetime.datetime.utcnow(),
            )
            embed.add_field(name="Title", value=title, inline=False)
            embed.add_field(name="Content", value=description, inline=False)
            embed.add_field(name="Author", value=ctx.message.author.name)
            embed.add_field(name="Session", value=current_leg_session_id)
            embed.add_field(
                name="Time of Submission (UTC)",
                value=datetime.datetime.utcnow(),
                inline=False,
            )

        await ctx.send(f"{config.YES} Your motion `{title}` was submitted for session #{current_leg_session_id}.")
        return embed

    @legislature.command(name="submit")
    @commands.cooldown(1, 30, commands.BucketType.user)
    @commands.max_concurrency(1, per=commands.BucketType.guild, wait=False)
    @checks.is_democraciv_guild()
    async def submit(self, ctx):
        """Submit a new bill or motion to the currently active session"""

        try:
            if self.is_cabinet(ctx.author):
                ctx.command.reset_cooldown(ctx)
        except exceptions.RoleNotFoundError:
            pass

        current_leg_session = await self.get_active_leg_session()

        if current_leg_session is None:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send(
                f"{config.NO} There is no open session.\n{config.HINT} The "
                f"{self.bot.mk.speaker_term} can open the next session with "
                f"`{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} session open` at any time."
            )

        if current_leg_session.status is not SessionStatus.SUBMISSION_PERIOD:
            ctx.command.reset_cooldown(ctx)

            if current_leg_session.status is SessionStatus.LOCKED:
                return await ctx.send(
                    f"{config.NO} The {self.bot.mk.speaker_term} has locked submissions for session "
                    f"#{current_leg_session.id}. You "
                    f"are not allowed to submit anything.\n{config.HINT} This session can be unlocked by the "
                    f"{self.bot.mk.speaker_term} in order "
                    f"to allow submissions again with `{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} session "
                    f"unlock`."
                )

            if current_leg_session.status is SessionStatus.VOTING_PERIOD:
                return await ctx.send(
                    f"{config.NO} Voting for session #{current_leg_session.id} has already started, so you "
                    f"cannot submit anything anymore."
                )

        if self.bot.mk.LEGISLATURE_MOTIONS_EXIST:
            reaction = await ctx.choose(
                f"{config.USER_INTERACTION_REQUIRED} Do you want to submit a motion or a bill? "
                f"React with {config.LEG_SUBMIT_BILL} for bill, and with "
                f"{config.LEG_SUBMIT_MOTION} for a motion."
                f"\n\n{config.HINT} *Motions lack a lot of features that bills have, "
                f"for example they cannot be passed into Law by the Government. They will not "
                f"show up in `{config.BOT_PREFIX}laws`, nor will they make it on the Legal Code. They can also not "
                f"be sponsored. If you want to submit something small "
                f"that results in some __temporary__ action and where it's not important to track if it passed, "
                f"use a motion, otherwise use a bill. __In most cases you should probably use bills.__ "
                f"Common examples for motions: `Motion to repeal Law #12`, or "
                f"`Motion to recall {self.bot.mk.legislator_term} XY`.*",
                reactions=[config.LEG_SUBMIT_BILL, config.LEG_SUBMIT_MOTION],
            )

            embed = None

            if not reaction:
                return

            if str(reaction.emoji) == config.LEG_SUBMIT_BILL:
                if not self.bot.mk.LEGISLATURE_EVERYONE_ALLOWED_TO_SUBMIT_BILLS:
                    if self.legislator_role not in ctx.author.roles:
                        return await ctx.send(
                            f"{config.NO} Only {self.bot.mk.LEGISLATURE_LEGISLATOR_NAME_PLURAL} are allowed to submit "
                            f"bills."
                        )

                embed = await self.submit_bill(ctx, current_leg_session.id)

            elif str(reaction.emoji) == config.LEG_SUBMIT_MOTION:
                ctx.command.reset_cooldown(ctx)

                if not self.bot.mk.LEGISLATURE_EVERYONE_ALLOWED_TO_SUBMIT_MOTIONS:
                    if self.legislator_role not in ctx.author.roles:
                        return await ctx.send(
                            f"{config.NO} Only {self.bot.mk.LEGISLATURE_LEGISLATOR_NAME_PLURAL} are allowed to submit "
                            f"motions."
                        )

                embed = await self.submit_motion(ctx, current_leg_session.id)
        else:
            if not self.bot.mk.LEGISLATURE_EVERYONE_ALLOWED_TO_SUBMIT_BILLS:
                if self.legislator_role not in ctx.author.roles:
                    return await ctx.send(
                        f"{config.NO} Only {self.bot.mk.LEGISLATURE_LEGISLATOR_NAME_PLURAL} are allowed to submit "
                        f"bills."
                    )

            embed = await self.submit_bill(ctx, current_leg_session.id)

        if embed is None:
            return

        if not self.is_cabinet(ctx.author):
            if self.speaker is not None:
                await self.bot.safe_send_dm(target=self.speaker, reason="leg_session_submit", embed=embed)
            if self.vice_speaker is not None:
                await self.bot.safe_send_dm(target=self.vice_speaker, reason="leg_session_submit", embed=embed)

    @legislature.command(name="pass", aliases=["p"])
    @checks.has_any_democraciv_role(mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER)
    async def pass_bill(self, ctx: context.CustomContext, bill_ids: Greedy[Bill]):
        """Mark one or multiple bills as passed from the {LEGISLATURE_NAME} to pass them into law

        **Example**
            `{PREFIX}{COMMAND} 12` will mark Bill #12 as passed from the {LEGISLATURE_NAME}
            `{PREFIX}{COMMAND} 45 46 49 51 52` will mark all those bills as passed"""

        if not bill_ids:
            return await ctx.send_help(ctx.command)

        def verify_bill(_ctx, b: Bill, last_session: Session):
            if last_session.id != b.session.id:
                return "You can only mark bills from the most recent session as passed."

            if last_session.status is not SessionStatus.CLOSED:
                return "You can only mark bills as passed if their session is closed."

        consumer = models.LegalConsumer(ctx=ctx, objects=bill_ids, action=models.BillStatus.pass_from_legislature)
        await consumer.filter(filter_func=verify_bill, last_session=await self.get_last_leg_session())

        if consumer.failed:
            await ctx.send(f":warning: The following bills can not be passed.\n{consumer.failed_formatted}")

        if not consumer.passed:
            return

        reaction = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want "
            f"to mark the following bills as passed from the {self.bot.mk.LEGISLATURE_NAME}?"
            f"\n{consumer.passed_formatted}"
        )

        if not reaction:
            return await ctx.send("Cancelled.")

        await consumer.consume(scheduler=self.pass_scheduler)
        await ctx.send(
            f"{config.YES} All bills were marked as passed from the {self.bot.mk.LEGISLATURE_NAME}.\n"
            f"{config.HINT} If the Legal Code needs to "
            f"be updated, the {self.bot.mk.speaker_term} can use my "
            f"`{config.BOT_PREFIX}laws export` command to make me generate a Google Docs Legal Code. "
        )

    @legislature.group(name="withdraw", aliases=["w"], hidden=True)
    @checks.is_democraciv_guild()
    async def withdraw(self, ctx):
        """Withdraw one or multiple bills or motions from the current session"""
        if ctx.invoked_subcommand is None:
            await ctx.send(
                f"{config.NO} You have to tell me whether you want to withdraw motions or bills!"
                " Take a look at the help page:"
            )
            await ctx.send_help(ctx.command)

    async def withdraw_objects(
            self,
            ctx: context.CustomContext,
            objects: typing.List[typing.Union[Bill, Motion]],
    ):
        if isinstance(objects[0], Bill):
            obj_name = "bill"
        else:
            obj_name = "motion"

        last_leg_session = await self.get_last_leg_session()

        def verify_object(_ctx, to_verify) -> str:
            if to_verify.session.closed_on:
                return f"The session during which this {obj_name} was submitted is not open anymore."

            if not self.is_cabinet(_ctx.author):
                if to_verify.submitter is not None and _ctx.author.id == to_verify.submitter.id:
                    if last_leg_session.status is SessionStatus.SUBMISSION_PERIOD:
                        allowed = True
                    else:
                        return f"The original submitter can only withdraw {obj_name}s during the Submission Period."
                else:
                    allowed = False
            else:
                allowed = True

            if not allowed:
                return (
                    f"Only the {_ctx.bot.mk.LEGISLATURE_CABINET_NAME} and the original submitter "
                    f"of this {obj_name} can withdraw it."
                )

        if obj_name == "bill":
            consumer = models.LegalConsumer(ctx=ctx, objects=objects, action=models.BillStatus.withdraw)
            await consumer.filter(filter_func=verify_object)

            if consumer.failed:
                await ctx.send(
                    f":warning: The following {obj_name}s can not be withdrawn by you.\n{consumer.failed_formatted}"
                )

            if not consumer.passed:
                return

            reaction = await ctx.confirm(
                f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want"
                f" to withdraw the following {obj_name}s from Session #{last_leg_session.id}?"
                f"\n{consumer.passed_formatted}"
            )

            if not reaction:
                return await ctx.send("Cancelled.")

            await consumer.consume()
            message = f"The following {obj_name}s were withdrawn by {ctx.author}.\n{consumer.passed_formatted}"

        elif obj_name == "motion":
            # doing it the old (ugly) way for motions since LegalConsumer is only for bills
            unverified_objects = []

            for obj in objects:
                error = verify_object(ctx, obj)
                if error:
                    unverified_objects.append((obj, error))

            if unverified_objects:
                objects = [o for o in objects if o not in list(map(list, zip(*unverified_objects)))[0]]

                error_messages = "\n".join(
                    [f"-  **{_object.name}** (#{_object.id}): _{reason}_" for _object, reason in unverified_objects]
                )
                await ctx.send(f":warning: The following {obj_name}s can not be withdrawn by you.\n{error_messages}")

            if not objects:
                return

            pretty_objects = "\n".join([f"-  **{_object.name}** (#{_object.id})" for _object in objects])
            are_you_sure = await ctx.confirm(
                f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want"
                f" to withdraw the following {obj_name}s from Session #{last_leg_session.id}?"
                f"\n{pretty_objects}"
            )

            if not are_you_sure:
                return await ctx.send("Cancelled.")

            for obj in objects:
                await obj.withdraw()

            message = f"The following {obj_name}s were withdrawn by {ctx.author}.\n{pretty_objects}"

        await ctx.send(f"{config.YES} All {obj_name}s were withdrawn.")

        if not self.is_cabinet(ctx.author):
            if self.speaker is not None:
                await self.bot.safe_send_dm(target=self.speaker, reason="leg_session_withdraw", message=message)
            if self.vice_speaker is not None:
                await self.bot.safe_send_dm(
                    target=self.vice_speaker,
                    reason="leg_session_withdraw",
                    message=message,
                )

    @withdraw.command(name="bill", aliases=["b"])
    @checks.is_democraciv_guild()
    async def withdrawbill(self, ctx: context.CustomContext, bill_ids: Greedy[Bill]):
        """Withdraw one or multiple bills from the current session

        The {speaker_term} can withdraw every submitted bill during both the Submission Period and the Voting Period.
           The original submitter of the bill can only withdraw their own bill during the Submission Period.

        **Example**
            `{PREFIX}{COMMAND} 56` will withdraw bill #56
            `{PREFIX}{COMMAND} 12 13 14 15 16` will withdraw all those bills"""

        if not bill_ids:
            return await ctx.send_help(ctx.command)

        await self.withdraw_objects(ctx, bill_ids)

    @withdraw.command(name="motion", aliases=["m"])
    @checks.is_democraciv_guild()
    async def withdrawmotion(self, ctx: context.CustomContext, motion_ids: Greedy[Motion]):
        """Withdraw one or multiple motions from the current session

        The {speaker_term} can withdraw every submitted motion during both the Submission Period and the Voting Period.
           The original submitter of the motion can only withdraw their own motion during the Submission Period.

        **Example**
            `{PREFIX}{COMMAND} 56` will withdraw motion #56
            `{PREFIX}{COMMAND} 12 13 14 15 16` will withdraw all those motions"""

        if not motion_ids:
            return await ctx.send_help(ctx.command)

        await self.withdraw_objects(ctx, motion_ids)

    @legislature.command(name="override", aliases=["ov"], hidden=True, enabled=False)
    @checks.has_any_democraciv_role(mk.DemocracivRole.SPEAKER, mk.DemocracivRole.VICE_SPEAKER)
    async def override(self, ctx: context.CustomContext, bill_ids: Greedy[Bill]):
        """Override the veto of one or multiple bills to pass them into law

        **Example**
           `{PREFIX}{COMMAND} 56`
           `{PREFIX}{COMMAND} 12 13 14 15 16`"""

        if not bill_ids:
            return await ctx.send_help(ctx.command)

        consumer = models.LegalConsumer(ctx=ctx, objects=bill_ids, action=models.BillStatus.override_veto)
        await consumer.filter()

        if consumer.failed:
            await ctx.send(
                f":warning: The vetoes of the following bills can not be overridden.\n{consumer.failed_formatted}"
            )

        if not consumer.passed:
            return

        reaction = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want "
            f"to override the {self.bot.mk.MINISTRY_NAME}'s veto of the following "
            f"bills?\n{consumer.passed_formatted}"
        )

        if not reaction:
            return await ctx.send("Cancelled.")

        await consumer.consume(scheduler=self.override_scheduler)
        await ctx.send(
            f"{config.YES} The vetoes of all bills were overridden, and all bills are active laws and in "
            f"`{config.BOT_PREFIX}laws` now."
        )

    @legislature.command(name="sponsor", aliases=["sp", "cosponsor", "second"])
    @checks.has_democraciv_role(mk.DemocracivRole.LEGISLATOR)
    async def sponsor(self, ctx: context.CustomContext, bill_ids: Greedy[Bill]):
        """Show your support for one or multiple bills by sponsoring them

        **Example**
           `{PREFIX}{COMMAND} 56`
           `{PREFIX}{COMMAND} 12 13 14 15 16`"""

        if not bill_ids:
            return await ctx.send_help(ctx.command)

        consumer = models.LegalConsumer(ctx=ctx, objects=bill_ids, action=models.BillStatus.sponsor)

        def filter_sponsor(_ctx, _bill, **kwargs):
            if _ctx.author.id == _bill.submitter.id:
                return "The bill's author cannot sponsor their own bill."

            if _ctx.author in _bill.sponsors:
                return "You already sponsored this bill."

        await consumer.filter(filter_func=filter_sponsor, sponsor=ctx.author)

        if consumer.failed:
            await ctx.send(f":warning: The following bills cannot be sponsored.\n{consumer.failed_formatted}")

        if not consumer.passed:
            return

        reaction = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want "
            f"to sponsor the following bills?\n{consumer.passed_formatted}"
        )

        if not reaction:
            return await ctx.send("Cancelled.")

        await consumer.consume(sponsor=ctx.author)
        await ctx.send(
            f"{config.YES} All bills were sponsored by you. Your name is now on the list of "
            f"sponsors on the detail pages `{config.BOT_PREFIX}{self.bot.mk.LEGISLATURE_COMMAND} "
            f"bill <bill_id>` for these bills."
        )

    @legislature.command(name="unsponsor", aliases=["usp"])
    @checks.has_democraciv_role(mk.DemocracivRole.LEGISLATOR)
    async def unsponsor(self, ctx: context.CustomContext, bill_ids: Greedy[Bill]):
        """Remove yourself from the list of sponsors of one or multiple bills

        **Example**
           `{PREFIX}{COMMAND} 56`
           `{PREFIX}{COMMAND} 12 13 14 15 16`"""

        if not bill_ids:
            return await ctx.send_help(ctx.command)

        consumer = models.LegalConsumer(ctx=ctx, objects=bill_ids, action=models.BillStatus.unsponsor)

        def filter_sponsor(_ctx, _bill, **kwargs):
            if _ctx.author not in _bill.sponsors:
                return "You are not a sponsor of this bill."

        await consumer.filter(filter_func=filter_sponsor, sponsor=ctx.author)

        if consumer.failed:
            await ctx.send(f":warning: The following bills cannot be unsponsored.\n{consumer.failed_formatted}")

        if not consumer.passed:
            return

        reaction = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want "
            f"to remove yourself from the list of sponsors of the following bills?\n{consumer.passed_formatted}"
        )

        if not reaction:
            return await ctx.send("Cancelled.")

        await consumer.consume(sponsor=ctx.author)
        await ctx.send(f"{config.YES} You were removed from the list of sponsors from all bills.")

    @legislature.command(name="resubmit", aliases=["rs"])
    async def resubmit(self, ctx: context.CustomContext, bill_ids: Greedy[Bill]):
        """Resubmit any bills that failed in the {LEGISLATURE_NAME} to the currently active session

        **Example**
           `{PREFIX}{COMMAND} 56`
           `{PREFIX}{COMMAND} 12 13 14 15 16`"""

        if not bill_ids:
            return await ctx.send_help(ctx.command)

        consumer = models.LegalConsumer(ctx=ctx, objects=bill_ids, action=models.BillStatus.resubmit)
        await consumer.filter()

        if consumer.failed:
            await ctx.send(f":warning: The following bills cannot be resubmitted.\n{consumer.failed_formatted}")

        if not consumer.passed:
            return

        reaction = await ctx.confirm(
            f"{config.USER_INTERACTION_REQUIRED} Are you sure that you want "
            f"to resubmit the following bills to the current session?\n{consumer.passed_formatted}"
        )

        if not reaction:
            return await ctx.send("Cancelled.")

        await consumer.consume()
        await ctx.send(f"{config.YES} All bills were resubmitted to the current session.")

    def _format_stats(self, *, record: typing.List[asyncpg.Record], record_key: str, stats_name: str) -> str:
        """Prettifies the dicts used in generate_leg_statistics() to strings"""

        record_as_list = [r[record_key] for r in record]
        counter = dict(collections.Counter(record_as_list))
        sorted_dict = {k: v for k, v in sorted(counter.items(), key=lambda item: item[1], reverse=True)}
        fmt = []

        for i, (key, value) in enumerate(sorted_dict.items(), start=1):
            if self.bot.get_user(key) is not None:
                if i > 5:
                    break

                if value == 1:
                    sts_name = stats_name[:-1]
                else:
                    sts_name = stats_name

                fmt.append(f"{i}. {self.bot.get_user(key).mention} with {value} {sts_name}")

        return "\n".join(fmt) or "None"

    async def _get_leg_stats(self, ctx):
        # todo fix this

        query = """SELECT COUNT(id) FROM legislature_session
                   UNION ALL
                   SELECT COUNT(id) FROM bill
                   UNION ALL
                   SELECT COUNT(id) FROM bill WHERE status = $1
                   UNION ALL
                   SELECT COUNT(id) FROM motion"""

        amounts = await self.bot.db.fetch(query, models.BillIsLaw.flag.value)

        submitter = await self.bot.db.fetch("SELECT submitter from bill")
        pretty_top_submitter = self._format_stats(record=submitter, record_key="submitter", stats_name="bills")

        speaker = await self.bot.db.fetch("SELECT speaker from legislature_session")
        pretty_top_speaker = self._format_stats(record=speaker, record_key="speaker", stats_name="sessions")

        lawmaker = await self.bot.db.fetch("SELECT submitter from bill WHERE status = $1", models.BillIsLaw.flag.value)
        pretty_top_lawmaker = self._format_stats(record=lawmaker, record_key="submitter", stats_name="laws")

        embed = text.SafeEmbed()
        embed.set_author(
            icon_url=self.bot.mk.NATION_ICON_URL,
            name=f"Statistics for the " f"{self.bot.mk.NATION_ADJECTIVE} " f"{self.bot.mk.LEGISLATURE_NAME}",
        )

        general_value = (
            f"Sessions: {amounts[0]['count']}\nSubmitted Bills: {amounts[1]['count']}\n"
            f"Submitted Motions: {amounts[3]['count']}\nActive Laws: {amounts[2]['count']}"
        )

        embed.add_field(name="General Statistics", value=general_value)
        embed.add_field(
            name=f"Top {self.bot.mk.speaker_term}s of the {self.bot.mk.LEGISLATURE_NAME}",
            value=pretty_top_speaker,
            inline=False,
        )
        embed.add_field(name="Top Bill Submitters", value=pretty_top_submitter, inline=False)
        embed.add_field(name="Top Lawmakers", value=pretty_top_lawmaker, inline=False)
        await ctx.send(embed=embed)

    @legislature.command(name="statistics", aliases=["stat", "stats", "statistic"])
    async def stats(
            self,
            ctx,
            *,
            person: typing.Union[
                converter.CaseInsensitiveMember, converter.CaseInsensitiveUser, converter.FuzzyCIMember
            ] = None,
    ):
        """Statistics about the {LEGISLATURE_NAME} or a specific person

        **Example**
        `{PREFIX}{COMMAND}` to get the overall statistics about the {LEGISLATURE_NAME}
        `{PREFIX}{COMMAND} DerJonas` to get personalized statistics for that person"""

        if not person:
            return await self._get_leg_stats(ctx)

        query = """SELECT COUNT(*) FROM bill WHERE submitter = $1
                   UNION ALL
                   SELECT COUNT(*) FROM bill WHERE submitter = $1 AND status = $2
                   UNION ALL
                   SELECT COUNT(*) FROM motion WHERE submitter = $1
                   UNION ALL
                   SELECT COUNT(id) FROM bill_sponsor WHERE sponsor = $1
                   UNION ALL
                   SELECT COUNT(bill_sponsor.sponsor) FROM bill_sponsor JOIN bill ON bill_sponsor.bill_id = bill.id WHERE bill.submitter = $1"""

        _stats = await self.bot.db.fetch(query, person.id, models.BillIsLaw.flag.value)

        embed = text.SafeEmbed()
        embed.set_author(
            icon_url=person.avatar_url_as(static_format="png"),
            name=f"{person.display_name} in the " f"{self.bot.mk.NATION_ADJECTIVE} " f"{self.bot.mk.LEGISLATURE_NAME}",
        )

        embed.add_field(name="Bill Submissions", value=_stats[0]["count"], inline=True)
        embed.add_field(name="Motion Submissions", value=_stats[2]["count"], inline=True)
        embed.add_field(name="Amount of Laws written", value=_stats[1]["count"], inline=False)
        embed.add_field(name="Amount of Bills sponsored", value=_stats[3]["count"], inline=False)
        embed.add_field(name="Amount of Sponsors for own Bills", value=_stats[4]["count"], inline=False)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Legislature(bot))
