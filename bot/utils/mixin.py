import collections
import datetime
import typing
import asyncpg
import discord

from bot.config import mk, config
from bot.utils import exceptions, context, models, paginator, text, converter


def _make_property(role: mk.DemocracivRole):
    return property(lambda self: self._safe_get_member(role))


class FullTextSearchView(text.PromptView):

    @discord.ui.button(
        label="Yes, perform full-text search",
        style=discord.ButtonStyle.gray,
        emoji="\U0001f50d",
    )
    async def full_text_search(self, interaction, button):
        await interaction.response.defer()
        self.result = True
        self.stop()


class ReadDocumentView(text.PromptView):

    webhook = None

    # async def interaction_check(self, interaction: discord.Interaction) -> bool:
    #    return True

    @discord.ui.button(
        label="Read Document", style=discord.ButtonStyle.grey, emoji="\U0001f4c3"
    )
    async def on_button(self, interaction, button):
        await interaction.response.defer()
        self.result = True
        self.webhook = interaction.followup
        self.stop()


class SessionKindChooseView(text.PromptView):
    @discord.ui.button(label="Regular", style=discord.ButtonStyle.primary)
    async def regular(self, interaction, button):
        await interaction.response.defer()
        self.result = models.SessionKind.REGULAR
        self.stop()

    @discord.ui.button(label="Emergency", style=discord.ButtonStyle.danger)
    async def emergency(self, interaction, button):
        await interaction.response.defer()
        self.result = models.SessionKind.EMERGENCY
        self.stop()


class SessionChoiceButton(discord.ui.Button):
    def __init__(self, session: models.Session):
        super().__init__(
            label=session.display_name,
            style=(
                discord.ButtonStyle.danger
                if session.is_emergency
                else discord.ButtonStyle.primary
            ),
        )
        self.session = session

    async def callback(self, interaction):
        await interaction.response.defer()
        self.view.result = self.session
        self.view.stop()


class SessionChooseView(text.PromptView):
    def __init__(self, ctx, *, sessions: typing.Sequence[models.Session]):
        super().__init__(ctx)
        for session in sessions:
            self.add_item(SessionChoiceButton(session))


def add_submit_session_choice(
    modal: discord.ui.Modal, sessions: typing.Sequence[models.Session]
):
    sessions = list(sessions)
    modal.submit_sessions = sessions
    modal.default_session_id = sessions[0].id if len(sessions) == 1 else None
    modal.session_choice = None

    if len(sessions) <= 1:
        return

    modal.session_choice = discord.ui.Label(
        text="Session",
        description="Choose which open session this submission belongs to.",
        component=discord.ui.Select(
            placeholder="Choose a session",
            options=[
                discord.SelectOption(label=session.display_name, value=str(session.id))
                for session in sessions
            ],
        ),
    )
    modal.add_item(modal.session_choice)


def get_submit_session_choice_id(modal: discord.ui.Modal) -> typing.Optional[int]:
    session_choice = getattr(modal, "session_choice", None)
    if session_choice is None:
        return getattr(modal, "default_session_id", None)

    values = session_choice.component.values
    if not values:
        return None

    return int(values[0])


class GovernmentMixin:
    def __init__(self, b):
        self.bot = b

    def _safe_get_member(self, role) -> typing.Optional[discord.Member]:
        try:
            return self.bot.get_democraciv_role(role).members[0]
        except (IndexError, exceptions.RoleNotFoundError):
            return None

    async def _paginate_all_(self, ctx, *, model):
        per_page = None

        if model is models.Bill:
            all_objects = await self.bot.db.fetch("SELECT id FROM bill ORDER BY id;")
        elif model is models.Law:
            all_objects = await self.bot.db.fetch(
                "SELECT id FROM bill WHERE status = $1 ORDER BY id;",
                models.BillIsLaw.flag.value,
            )
        elif model is models.Motion:
            per_page = 12
            all_objects = await self.bot.db.fetch("SELECT id FROM motion ORDER BY id;")

        formatted = []

        for record in all_objects:
            obj = await model.convert(ctx, record["id"])
            formatted.append(f"* {obj.formatted}")

        if model is models.Law:
            title = f"All Laws in {self.bot.mk.NATION_NAME}"
            empty_message = f"There are no laws yet."
        else:
            title = f"All Submitted {model.__name__}s — Senate & Commons"
            empty_message = f"No one has submitted any {model.__name__.lower()}s yet."

        pages = paginator.SimplePages(
            entries=formatted,
            icon=self.bot.mk.NATION_ICON_URL,
            author=title,
            empty_message=empty_message,
            per_page=per_page,
        )
        await ctx.send(
            f"-# {config.HINT} Check out [laws.democraciv.com](<https://laws.democraciv.com>) as well!"
        )
        await pages.start(ctx)

    async def _detail_view(
        self,
        ctx: context.CustomContext,
        *,
        obj: typing.Union[models.Bill, models.Motion, models.Law],
    ):
        embed = text.SafeEmbed(
            title=f"{obj.name} (#{obj.id})", description=obj.description, url=obj.link
        )

        if obj.submitter is not None:
            embed.set_author(
                name=f"Submitted by {obj.submitter.name}",
                icon_url=obj.submitter.display_avatar.url,
            )
            submitted_by_value = f"{obj.submitter.mention} {obj.submitter}"
        else:
            submitted_by_value = f"*Unknown Person*"

        embed.add_field(name="Submitter", value=submitted_by_value, inline=True)
        # embed.add_field(name="laws.democraciv.com", value=f"[Link](https://laws.democraciv.com/{obj.model.lower()}/{obj.id})", inline=True)

        if isinstance(obj, models.Bill) and not isinstance(obj, models.Law):
            if obj.session.house in models.HOUSE_NAMES:
                embed.add_field(
                    name="Orig. in Chamber", value=obj.origin_house_name, inline=True
                )
                embed.add_field(name="Type", value=obj.type_name, inline=True)
                # embed.add_field(name="laws.democraciv.com", value=f"[Link](https://laws.democraciv.com/bill/{obj.id})", inline=True)
            else:
                is_vetoable = "Yes" if obj.is_vetoable else "No"
                embed.add_field(name="Vetoable", value=is_vetoable, inline=True)

            embed.add_field(
                name="Status",
                value=obj.status.emojified_status(verbose=True),
                inline=False,
            )

            if obj.executive_deadline_at is not None:
                embed.add_field(
                    name="Executive Deadline",
                    value=f"<t:{int(obj.executive_deadline_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:R> ",
                    inline=True,
                )

            if obj.sponsors:
                fmt_sponsors = "\n".join(
                    [f"{sponsor.mention} {sponsor}" for sponsor in obj.sponsors]
                )
                embed.add_field(name="Sponsors", value=fmt_sponsors, inline=False)

        if not isinstance(obj, models.Motion):
            # embed.add_field(name="laws.democraciv.com", value=f"[Link](https://laws.democraciv.com/motion/{obj.id})", inline=True)

            history = [
                f"* <t:{int(entry.date.timestamp())}:D> - {entry.note if entry.note else entry.after}"
                for entry in obj.history[:10]
            ]

            if history:
                embed.add_field(name="History", value="\n".join(history), inline=False)

            if not isinstance(obj, models.Law) and obj.status.is_law:
                embed.set_footer(text="This is an active law.")

            view = ReadDocumentView(ctx=ctx)
            await ctx.send(
                f"-# {config.HINT} Check out [laws.democraciv.com](<https://laws.democraciv.com/{obj.model.lower()}/{obj.id}>) as well!"
            )
            await ctx.send(embed=embed, view=view)
            do_continue = await view.prompt(silent=True)
            # followup = None

            # if mode == "private":
            #    # followup = view.webhook
            #    return

            if do_continue:
                # await self._show_bill_text(ctx, obj, ephemeral_webhook=followup)
                await self._show_bill_text(ctx, obj)
                return

        else:
            if obj.sponsors:
                fmt_sponsors = "\n".join(
                    [f"{sponsor.mention} {sponsor}" for sponsor in obj.sponsors]
                )
                embed.add_field(name="Sponsors", value=fmt_sponsors, inline=False)

            await ctx.send(
                f"-# {config.HINT} Check out [laws.democraciv.com](<https://laws.democraciv.com/{obj.model.lower()}/{obj.id}>) as well!"
            )
            await ctx.send(embed=embed)

    async def _show_bill_text(self, ctx, bill: models.Bill, *, ephemeral_webhook=None):
        leader_term = self.get_primary_leader_term_for_house(
            getattr(getattr(bill, "session", None), "house", None)
        )
        entries = bill.content.splitlines()
        entries.insert(
            0,
            f"[Link to the Google Docs document of this Bill]({bill.link})\n"
            f"*Am I showing you outdated or wrong text? Tell the {leader_term} to synchronize this text "
            f"with the Google Docs text of this bill with `{config.BOT_PREFIX}bill synchronize {bill.id}`.*\n\n",
        )
        pages = paginator.SimplePages(
            entries=entries,
            icon=self.bot.mk.NATION_ICON_URL,
            author=f"{bill.name} (#{bill.id})",
            ephemeral_webhook=ephemeral_webhook,
        )
        await ctx.send(
            f"-# {config.HINT} Check out [laws.democraciv.com](<https://laws.democraciv.com/bill/{bill.id}>) as well!"
        )
        await pages.start(ctx)

    async def generate_google_docs_legal_code(self):
        doc_url = "https://docs.google.com/document/d/1ywV_F70odxHh5fLcqcghpFOToPao85CjfT5Y_mYcml0/edit?usp=sharing"

        if not doc_url:
            return

        all_laws = await self.bot.db.fetch(
            "SELECT id, name, link FROM bill WHERE status = $1 ORDER BY id;",
            models.BillIsLaw.flag.value,
        )
        ugly_laws = [dict(r) for r in all_laws]
        date = discord.utils.utcnow().strftime("%B %d, %Y at %H:%M")

        result = await self.bot.run_apps_script(
            script_id="MMV-pGVACMhaf_DjTn8jfEGqnXKElby-M",
            function="generate_legal_code",
            parameters=[
                doc_url,
                {"name": self.bot.mk.NATION_FULL_NAME, "date": date},
                ugly_laws,
            ],
        )

        return result

    async def _search_model(self, ctx, *, model, query: str, return_model=False):
        if len(query) < 3:
            raise exceptions.DemocracivBotException(
                f"{config.NO} The query to search for has to be at least 3 characters long."
            )

        if model is models.Motion:
            found = await self.bot.db.fetch(
                "SELECT id from motion WHERE (lower(title) LIKE '%' || $1 || '%') OR"
                " (lower(description) LIKE '%' || $1 || '%') "
                "ORDER BY similarity(lower(title), $1) DESC LIMIT 20",
                query.lower(),
            )
            formatted = []

            for record in found:
                obj = await model.convert(ctx, record["id"])
                if return_model:
                    formatted.append(obj)
                else:
                    formatted.append(f"* {obj.formatted}")
        else:
            is_law = model is models.Law
            # First, search by name similarity
            async with self.bot.db.acquire() as con:
                results = await self._search_bill_by_name(
                    query, connection=con, search_laws=is_law, return_model=return_model
                )

                # Set word similarity threshold for search by tag
                await self._update_pg_trgm_similarity_threshold(0.4, connection=con)

                # Then, search by tag similarity
                # for word in query.split():
                #    if len(word) < 3 or word in (
                #        "the",
                #        "author",
                #        "authors",
                #        "date",
                #        "name",
                #        "and",
                #        "d/m/y",
                #        "type",
                #        "description",
                #        "by",
                #        "generated",
                #    ):
                #        continue

                result = await self._search_bill_by_tag(
                    query, connection=con, search_laws=is_law, return_model=return_model
                )
                if result:
                    results.update(result)

            formatted = list(results)

        return formatted

    async def _full_text_search_with_meilisearch(self, ctx, *, model, query):
        if model is models.Law:
            response = await self.bot.api_request(
                "POST",
                "document/search",
                json={"question": query, "index": "bill", "is_law": True},
            )

        else:
            response = await self.bot.api_request(
                "POST",
                "document/search",
                json={"question": query, "index": model.model.lower()},
            )

        if not response or response["result"]["error"]:
            raise exceptions.DemocracivBotException(f"{config.NO}.")

        print(response)

    async def _ai_embedding_search_with_meilisearch(self, ctx, *, model, query):
        if model is models.Law:
            response = await self.bot.api_request(
                "POST",
                "document/search",
                json={"question": query, "index": "bill", "is_law": True},
            )
        else:
            response = await self.bot.api_request(
                "POST",
                "document/search",
                json={"question": query, "index": "bill", "is_law": True},
            )

    async def prepare_full_text_search_paginator(
        self, ctx, query, *, index="bill", is_law=False
    ):
        if index == "bill":
            model = models.Law if is_law else models.Bill
        else:
            model = models.Motion

        response = await self.bot.api_request(
            "POST",
            "document/search",
            json={"question": query, "index": index, "is_law": is_law},
        )

        if not response or not response["result"]["hits"]:
            return None

        fmt = [
            f"Full-text search is a work-in-progress.\nKnown issue: This **only shows 1 search result per {model.model}**, even if there were more occurrences found.\n"
        ]

        for hit in response["result"]["hits"]:
            try:
                obj = await model.convert(ctx, hit["id"])
            except Exception:
                continue

            trimmed = hit["_formatted"]["content"].strip()
            txt = discord.utils.escape_markdown(trimmed)
            txt = txt.replace("<DBS>", "[**")
            txt = txt.replace(
                "<DBE>", "**](https://this-is-not-a-real-url.democraciv.com)"
            )
            fmt.append(f"**__{obj.formatted}__**")
            fmt.append(f"{txt}\n")

        return paginator.SimplePages(
            entries=fmt,
            icon=self.bot.mk.NATION_ICON_URL,
            author=f"[BETA] Full-text search results for '{query}'",
        )

    async def _from_person_model(self, ctx, *, member_or_party, model, paginate=True):
        member = member_or_party or ctx.author
        submit_term = "written" if model is models.Law else "submitted"
        per_page = None

        if isinstance(member, converter.PoliticalParty):
            name = member.role.name
            members = [m.id for m in member.role.members]
            empty = (
                f"No member of {name} has {submit_term} a {model.__name__.lower()} yet."
            )
            title = f"{model.__name__}s from members of {name}"
            icon = await member.get_logo() or self.bot.mk.NATION_ICON_URL or None
        else:
            name = member.display_name
            members = [member.id]
            empty = f"{name} hasn't {submit_term} any {model.__name__.lower()}s yet."
            title = f"{model.__name__}s from {name}"
            icon = member.display_avatar.url

        if model is models.Bill:
            objs_from_thing = await self.bot.db.fetch(
                "SELECT id FROM bill WHERE submitter = ANY($1::bigint[]) ORDER BY id;",
                members,
            )

        elif model is models.Law:
            objs_from_thing = await self.bot.db.fetch(
                "SELECT id FROM bill WHERE submitter = ANY($1::bigint[]) AND status = $2 ORDER BY id;",
                members,
                models.BillIsLaw.flag.value,
            )
        else:
            objs_from_thing = await self.bot.db.fetch(
                "SELECT id FROM motion WHERE submitter = ANY($1::bigint[]) ORDER BY id;",
                members,
            )
            per_page = 12

        formatted = []

        for record in objs_from_thing:
            obj = await model.convert(ctx, record["id"])
            formatted.append(f"* {obj.formatted}")

        if not paginate:
            return formatted

        pages = paginator.SimplePages(
            entries=formatted,
            author=title,
            icon=icon,
            per_page=per_page,
            empty_message=empty,
        )
        await pages.start(ctx)

    async def _search_bill_by_name(
        self, name: str, connection=None, search_laws: bool = False, return_model=False
    ) -> typing.Dict[typing.Union[models.Bill, models.Law, str], None]:
        """Search for bills by their name, returns list with prettified strings of found bills"""

        con = connection or self.bot.db

        model = models.Bill if not search_laws else models.Law

        if search_laws:
            objs = await con.fetch(
                "SELECT id FROM bill WHERE (lower(name) LIKE '%' || $1 || '%' OR lower(name) % $1) AND status = $2"
                " ORDER BY similarity(lower(name), $1) DESC LIMIT 10;",
                name.lower(),
                models.BillIsLaw.flag.value,
            )
        else:
            objs = await con.fetch(
                "SELECT id FROM bill WHERE (lower(name) LIKE '%' || $1 || '%' OR lower(name) % $1)"
                " ORDER BY similarity(lower(name), $1) DESC LIMIT 10;",
                name.lower(),
            )

        found = {}

        for record in objs:
            obj = await model.convert(context.MockContext(self.bot), record["id"])
            if return_model:
                found[obj] = None
            else:
                found[f"* {obj.formatted}"] = None

        return found

    async def _search_bill_by_tag(
        self,
        tag: str,
        connection=None,
        search_laws: bool = False,
        *,
        return_model=False,
    ) -> typing.Dict[typing.Union[models.Bill, models.Law, str], None]:
        """Search for bills by their tag(s), returns list with prettified strings of found laws"""

        con = connection or self.bot.db

        model = models.Bill if not search_laws else models.Law

        if search_laws:
            found_bills = await con.fetch(
                "SELECT bill_lookup_tag.bill_id FROM bill_lookup_tag "
                "JOIN bill on bill_lookup_tag.bill_id=bill.id "
                "WHERE (bill_lookup_tag.tag % $1 OR bill_lookup_tag.tag LIKE '%' || $1 || '%') AND bill.status = $2 ORDER BY bill_lookup_tag.tag <-> $1",
                tag.lower(),
                models.BillIsLaw.flag.value,
            )
        else:
            found_bills = await con.fetch(
                "SELECT bill_id FROM bill_lookup_tag WHERE tag % $1 OR tag LIKE '%' || $1 || '%' ORDER BY tag <-> $1",
                tag.lower(),
            )

        # Abuse dict as ordered set
        formatted = {}

        for record in found_bills:
            obj = await model.convert(context.MockContext(self.bot), record["bill_id"])
            if return_model:
                formatted[obj] = None
            else:
                formatted[f"* {obj.formatted}"] = None

        return formatted

    async def _update_pg_trgm_similarity_threshold(
        self, threshold: float = 0.3, connection=None
    ):
        # I couldn't figure out how to make the setting persist in all sessions from the connection pool, so
        # we just set it every time per connection

        con = connection or self.bot.db
        await con.execute(f"SET pg_trgm.similarity_threshold = {threshold}")

    @staticmethod
    def is_google_doc_link(link: str) -> bool:
        """Checks whether a link is a valid Google Docs or Google Forms link"""

        valid_google_docs_url_strings = (
            "https://docs.google.com",
            "https://drive.google.com",
            "https://forms.gle",
            "https://goo.gl/forms",
        )

        return len(link) >= 15 and link.startswith(valid_google_docs_url_strings)

    async def get_open_leg_sessions(
        self,
        house=None,
        *,
        session_kind: typing.Optional[models.SessionKind] = None,
        status: typing.Optional[models.SessionStatus] = None,
    ) -> typing.List[models.Session]:
        if isinstance(session_kind, str):
            session_kind = models.SessionKind(session_kind)

        query = ["SELECT id FROM legislature_session WHERE status != 'Closed'"]
        args = []

        if house is not None:
            args.append(house)
            query.append(f"AND house = ${len(args)}")

        if session_kind is not None:
            args.append(session_kind.value)
            query.append(f"AND session_kind = ${len(args)}")

        if status is not None:
            args.append(status.value)
            query.append(f"AND status = ${len(args)}")

        query.append("ORDER BY CASE session_kind WHEN 'Regular' THEN 0 ELSE 1 END, id")
        records = await self.bot.db.fetch(" ".join(query), *args)
        return [
            await models.Session.convert(context.MockContext(self.bot), record["id"])
            for record in records
        ]

    async def get_active_leg_session(
        self,
        house=None,
        *,
        session_kind: typing.Optional[models.SessionKind] = None,
    ) -> typing.Optional[models.Session]:
        sessions = await self.get_open_leg_sessions(
            house=house, session_kind=session_kind
        )
        if len(sessions) == 1:
            return sessions[0]

    async def get_last_leg_session(
        self,
        house=None,
        *,
        session_kind: typing.Optional[models.SessionKind] = None,
    ) -> typing.Optional[models.Session]:
        if isinstance(session_kind, str):
            session_kind = models.SessionKind(session_kind)

        query = ["SELECT MAX(id) FROM legislature_session"]
        args = []

        if house is not None:
            args.append(house)
            query.append(f"WHERE house = ${len(args)}")

        if session_kind is not None:
            args.append(session_kind.value)
            query.append(
                f"{'AND' if house is not None else 'WHERE'} session_kind = ${len(args)}"
            )

        session_id = await self.bot.db.fetchval(" ".join(query), *args)

        if session_id is not None:
            return await models.Session.convert(
                context.MockContext(self.bot), session_id
            )

    async def prompt_for_session_kind(
        self,
        ctx: context.CustomContext,
        *,
        house: str,
        action: str,
    ) -> typing.Optional[models.SessionKind]:
        view = SessionKindChooseView(ctx)
        await ctx.send(
            f"{config.USER_INTERACTION_REQUIRED} Which kind of "
            f"{models.display_house_name(house)} session do you want to {action}?",
            view=view,
        )
        return await view.prompt()

    async def prompt_for_leg_session(
        self,
        ctx: context.CustomContext,
        *,
        sessions: typing.Sequence[models.Session],
        action: str,
        ephemeral: typing.Optional[bool] = None,
        silent: bool = False,
    ) -> typing.Optional[models.Session]:
        view = SessionChooseView(ctx, sessions=sessions)
        kwargs = {"view": view}
        if ephemeral is not None:
            kwargs["ephemeral"] = ephemeral

        await ctx.send(
            f"{config.USER_INTERACTION_REQUIRED} Which session do you want to {action}?",
            **kwargs,
        )
        return await view.prompt(silent=silent)

    async def resolve_active_leg_session_for_text_command(
        self,
        ctx: context.CustomContext,
        *,
        house: str,
        action: str,
        status: typing.Optional[models.SessionStatus] = None,
    ) -> typing.Optional[models.Session]:
        sessions = await self.get_open_leg_sessions(house=house, status=status)

        if len(sessions) == 1:
            return sessions[0]

        if len(sessions) > 1:
            return await self.prompt_for_leg_session(
                ctx, sessions=sessions, action=action
            )

        return None

    def can_member_submit_kind(self, member: discord.Member, *, kind: str) -> bool:
        if kind == "bill" and self.bot.mk.LEGISLATURE_EVERYONE_ALLOWED_TO_SUBMIT_BILLS:
            return True

        if (
            kind == "motion"
            and self.bot.mk.LEGISLATURE_EVERYONE_ALLOWED_TO_SUBMIT_MOTIONS
        ):
            return True

        return bool(
            isinstance(member, discord.Member)
            and self.legislator_role
            and self.legislator_role in member.roles
        )

    def submission_session_rejection(
        self,
        member: discord.Member,
        *,
        house: str,
        session: models.Session,
    ) -> typing.Optional[str]:
        if session.house != house:
            return (
                f"{config.NO} That session does not belong to "
                f"the {models.display_house_name(house)}."
            )

        if session.status is models.SessionStatus.SUBMISSION_PERIOD:
            return None

        if session.status is models.SessionStatus.LOCKED:
            if isinstance(member, discord.Member) and self.is_cabinet_for_house(
                member, house
            ):
                return None

            return (
                f"{config.NO} The {self.get_primary_leader_term_for_house(house)} "
                f"has locked submissions for {session.display_name}."
            )

        if session.status is models.SessionStatus.VOTING_PERIOD:
            return f"{config.NO} Voting for {session.display_name} has already started."

        if session.status is models.SessionStatus.CLOSED:
            return f"{config.NO} {session.display_name} is already closed."

        return f"{config.NO} {session.display_name} is not accepting submissions right now."

    async def get_submission_eligible_leg_sessions(
        self,
        *,
        house: str,
        member: discord.Member,
        session_kind: typing.Optional[models.SessionKind] = None,
    ) -> typing.List[models.Session]:
        sessions = await self.get_open_leg_sessions(
            house=house, session_kind=session_kind
        )
        return [
            session
            for session in sessions
            if self.submission_session_rejection(member, house=house, session=session)
            is None
        ]

    def submission_session_unavailable_message(
        self,
        *,
        house: str,
        member: discord.Member,
        sessions: typing.Sequence[models.Session],
        session_kind: typing.Optional[models.SessionKind] = None,
    ) -> str:
        house_name = models.display_house_name(house)

        if not sessions:
            suffix = (
                f" {session_kind.value.lower()}" if session_kind is not None else ""
            )
            return (
                f"{config.NO} There is no open{suffix} {house_name} session.\n"
                f"{config.HINT} The {self.get_primary_leader_term_for_house(house)} "
                f"can open the next session at any time."
            )

        if len(sessions) == 1:
            rejection = self.submission_session_rejection(
                member, house=house, session=sessions[0]
            )
            if rejection:
                return rejection

        statuses = ", ".join(
            f"{session.display_name}: {session.status.value}" for session in sessions
        )
        return (
            f"{config.NO} There is no {house_name} session accepting submissions "
            f"right now.\n{config.HINT} {statuses}"
        )

    async def resolve_submit_session_from_modal(
        self,
        ctx,
        *,
        house: str,
        session_id: typing.Optional[int],
    ) -> typing.Tuple[typing.Optional[models.Session], typing.Optional[str]]:
        if session_id is None:
            return None, f"{config.NO} You need to choose a session."

        try:
            session = await models.Session.convert(ctx, session_id)
        except exceptions.NotFoundError as exc:
            return None, exc.message

        rejection = self.submission_session_rejection(
            ctx.author, house=house, session=session
        )
        if rejection:
            return None, rejection

        return session, None

    @staticmethod
    def bill_needs_cross_house_destination(
        bill: models.Bill, *, acting_house: str
    ) -> bool:
        if bill.is_procedure:
            return False

        if isinstance(bill.status, models.BillSubmitted):
            return True

        if isinstance(bill.status, models.BillFailedSenate):
            return acting_house == "senate" and bill.origin_house != "commons"

        if isinstance(bill.status, models.BillFailedCommons):
            return acting_house == "commons" and bill.origin_house != "senate"

        return False

    async def attach_pending_bills_to_session(
        self, *, house: str, session_id: int
    ) -> int:
        waiting_status = (
            models._BillStatusFlag.PASSED_SENATE_PENDING_COMMONS.value
            if house == "commons"
            else models._BillStatusFlag.PASSED_COMMONS_PENDING_SENATE.value
        )

        queued_bills = await self.bot.db.fetch(
            "SELECT id FROM bill WHERE status = $1 ORDER BY id",
            waiting_status,
        )
        bill_ids = [record["id"] for record in queued_bills]

        if not bill_ids:
            return 0

        await self.bot.db.execute(
            "UPDATE bill SET leg_session = $1 WHERE id = ANY($2::int[])",
            session_id,
            bill_ids,
        )
        await self.bot.db.executemany(
            "INSERT INTO bill_session (bill_id, leg_session) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            [(bill_id, session_id) for bill_id in bill_ids],
        )

        return len(bill_ids)

    class MockChannel:
        id = 0
        name = mention = "deleted channel"

        async def send(self, *args, **kwargs):
            pass

    @property
    def gov_announcements_channel(
        self,
    ) -> typing.Union[discord.TextChannel, MockChannel]:
        try:
            return self.bot.get_democraciv_channel(
                mk.DemocracivChannel.GOV_ANNOUNCEMENTS_CHANNEL
            )
        except exceptions.ChannelNotFoundError:
            return self.MockChannel()

    speaker = _make_property(mk.DemocracivRole.SPEAKER)
    vice_speaker = _make_property(mk.DemocracivRole.VICE_SPEAKER)
    senator_presiding = _make_property(mk.DemocracivRole.MK13_SENATOR_PRESIDING)
    chief_justice = _make_property(mk.DemocracivRole.CHIEF_JUSTICE)
    prime_minister = _make_property(mk.DemocracivRole.PRIME_MINISTER)
    lt_prime_minister = _make_property(mk.DemocracivRole.LT_PRIME_MINISTER)

    @property
    def speaker_role(self) -> typing.Optional[discord.Role]:
        try:
            return self.bot.get_democraciv_role(mk.DemocracivRole.SPEAKER)
        except exceptions.RoleNotFoundError:
            return None

    @property
    def vice_speaker_role(self) -> typing.Optional[discord.Role]:
        try:
            return self.bot.get_democraciv_role(mk.DemocracivRole.VICE_SPEAKER)
        except exceptions.RoleNotFoundError:
            return None

    @property
    def senator_presiding_role(self) -> typing.Optional[discord.Role]:
        try:
            return self.bot.get_democraciv_role(
                mk.DemocracivRole.MK13_SENATOR_PRESIDING
            )
        except exceptions.RoleNotFoundError:
            return None

    @property
    def legislator_role(self) -> typing.Optional[discord.Role]:
        try:
            return self.bot.get_democraciv_role(mk.DemocracivRole.LEGISLATOR)
        except exceptions.RoleNotFoundError:
            return None

    async def dm_legislators(self, *, message: str, reason: str):
        if not self.legislator_role:
            return

        for legislator in self.legislator_role.members:
            await self.bot.safe_send_dm(
                target=legislator, reason=reason, message=message
            )

    def is_cabinet(self, member: discord.Member) -> bool:
        return (
            self.speaker_role in member.roles or self.vice_speaker_role in member.roles
        )

    def get_house_for_object(self, obj) -> typing.Optional[str]:
        session = getattr(obj, "session", None)
        return getattr(session, "house", None)

    def get_primary_leader_term_for_house(self, house: typing.Optional[str]) -> str:
        if house == "senate":
            return self.bot.mk.senator_presiding_term

        if house == "commons":
            return self.bot.mk.speaker_term

        return self.bot.mk.LEGISLATURE_CABINET_NAME

    def get_cabinet_members_for_house(
        self, house: typing.Optional[str]
    ) -> typing.List[discord.Member]:
        if house == "senate":
            return [member for member in [self.senator_presiding] if member is not None]

        if house == "commons":
            return [member for member in [self.speaker, self.vice_speaker] if member]

        seen = set()
        members = []

        for member in [self.senator_presiding, self.speaker, self.vice_speaker]:
            if member is None or member.id in seen:
                continue

            seen.add(member.id)
            members.append(member)

        return members

    def is_cabinet_for_house(
        self, member: discord.Member, house: typing.Optional[str]
    ) -> bool:
        if house == "senate":
            return self.senator_presiding_role in member.roles

        if house == "commons":
            return (
                self.speaker_role in member.roles
                or self.vice_speaker_role in member.roles
            )

        return (
            self.senator_presiding_role in member.roles
            or self.speaker_role in member.roles
            or self.vice_speaker_role in member.roles
        )

    def can_member_sponsor_in_house(
        self, member: discord.Member, house: typing.Optional[str]
    ) -> bool:
        if house == "commons":
            return True

        if self.legislator_role is None:
            return False

        return self.legislator_role in member.roles

    @property
    def justice_role(self) -> typing.Optional[discord.Role]:
        return self.bot.get_democraciv_role(mk.DemocracivRole.JUSTICE)

    @property
    def judge_role(self) -> typing.Optional[discord.Role]:
        return self.bot.get_democraciv_role(mk.DemocracivRole.JUDGE)

    async def _build_legislature_overview_embed(self, house: str) -> text.SafeEmbed:
        is_senate = house == "senate"

        open_sessions = await self.get_open_leg_sessions(house=house)
        if not open_sessions:
            if is_senate:
                session_value = "There currently is no open session."
            else:
                session_value = "There currently is no open session at the Commons."
        else:
            session_value = "\n".join(
                f"{session.display_name} - {session.status.value}"
                for session in open_sessions
            )

        embed = text.SafeEmbed()

        if is_senate:
            author_name = (
                f"The {self.bot.mk.LEGISLATURE_NAME} of "
                f"{self.bot.mk.NATION_FULL_NAME}"
            )
            cabinet_title = self.bot.mk.LEGISLATURE_CABINET_NAME
            speaker_lines = []
            sp = self.senator_presiding
            if isinstance(sp, discord.Member):
                speaker_lines.append(
                    f"{self.bot.mk.senator_presiding_term}: "
                    f"{sp.mention} {discord.utils.escape_markdown(str(sp))}"
                )
            else:
                speaker_lines.append(f"{self.bot.mk.senator_presiding_term}: -")
        else:
            author_name = f"The Commons of {self.bot.mk.NATION_FULL_NAME}"
            cabinet_title = self.bot.mk.LEGISLATURE_CABINET_NAME
            speaker_lines = []
            speaker = self.speaker
            if isinstance(speaker, discord.Member):
                speaker_lines.append(
                    f"{self.bot.mk.speaker_term}: "
                    f"{speaker.mention} {discord.utils.escape_markdown(str(speaker))}"
                )
            else:
                speaker_lines.append(f"{self.bot.mk.speaker_term}: -")
            vice_speaker = self.vice_speaker
            if isinstance(vice_speaker, discord.Member):
                speaker_lines.append(
                    f"{self.bot.mk.vice_speaker_term}: "
                    f"{vice_speaker.mention} {discord.utils.escape_markdown(str(vice_speaker))}"
                )
            else:
                speaker_lines.append(f"{self.bot.mk.vice_speaker_term}: -")

        embed.set_author(
            icon_url=self.bot.mk.NATION_ICON_URL,
            name=author_name,
        )

        embed.add_field(name=cabinet_title, value="\n".join(speaker_lines))

        try:
            legislators = self.bot.get_democraciv_role(mk.DemocracivRole.LEGISLATOR)
            legislator_lines = [
                f"{l.mention} {discord.utils.escape_markdown(str(l))}"
                for l in legislators.members
            ] or ["-"]
            count = len(legislators.members)
        except exceptions.RoleNotFoundError:
            legislator_lines = ["-"]
            count = 0

        embed.add_field(
            name=f"{self.bot.mk.legislator_term}s ({count})",
            value="\n".join(legislator_lines),
            inline=False,
        )

        embed.add_field(
            name="Links",
            value=(
                f"[Constitution]({self.bot.mk.CONSTITUTION})\n"
                f"[Legal Code]({self.bot.mk.LEGAL_CODE}) "
                "*(try [laws.democraciv.com](https://laws.democraciv.com) too!)*\n"
                f"[Legislative Docket/Worksheet]({self.bot.mk.LEGISLATURE_DOCKET})\n"
                f"[Legislative Procedures]({self.bot.mk.LEGISLATURE_PROCEDURES})"
            ),
            inline=False,
        )

        session_label = (
            "Current Commons Session" if not is_senate else "Current Session"
        )
        embed.add_field(name=session_label, value=session_value, inline=False)

        return embed

    def get_justices(self) -> list:
        try:
            _justices = self.justice_role
        except exceptions.RoleNotFoundError:
            return None

        if isinstance(self.chief_justice, discord.Member):
            justices = [
                f"{justice.mention} {discord.utils.escape_markdown(str(justice))}"
                for justice in _justices.members
                if justice.id != self.chief_justice.id
            ]
            justices.insert(
                0,
                f"{self.chief_justice.mention} {discord.utils.escape_markdown(str(self.chief_justice))} **({self.bot.mk.COURT_CHIEF_JUSTICE_NAME})**",
            )
            return justices
        else:
            return [
                f"{justice.mention} {discord.utils.escape_markdown(str(justice))}"
                for justice in _justices.members
            ]

    def get_judges(self) -> list:
        try:
            _judges = self.judge_role
        except exceptions.RoleNotFoundError:
            return None

        return [
            f"{judge.mention} {discord.utils.escape_markdown(str(judge))}"
            for judge in _judges.members
        ]

    def format_stats(
        self, *, record: typing.List[asyncpg.Record], record_key: str, stats_name: str
    ) -> str:
        record_as_list = [r[record_key] for r in record]
        counter = dict(collections.Counter(record_as_list))
        sorted_dict = {
            k: v
            for k, v in sorted(counter.items(), key=lambda item: item[1], reverse=True)
        }
        fmt = []

        for i, (key, value) in enumerate(sorted_dict.items(), start=1):
            if self.bot.get_user(key) is not None:
                if i > 5:
                    break

                if value == 1:
                    sts_name = stats_name[:-1]
                else:
                    sts_name = stats_name

                fmt.append(
                    f"{i}. {self.bot.get_user(key).mention} with {value} {sts_name}"
                )

        return "\n".join(fmt) or "None"

    async def _build_government_overview_embed(self) -> text.SafeEmbed:
        embed = text.SafeEmbed()
        embed.set_author(
            name=f"Government of {self.bot.mk.NATION_FULL_NAME}",
            icon_url=self.bot.mk.NATION_ICON_URL,
        )

        justices = self.get_justices() or ["-"]

        minister_value = []

        if isinstance(self.prime_minister, discord.Member):
            minister_value.append(
                f"{self.bot.mk.pm_term}: {self.prime_minister.mention} {discord.utils.escape_markdown(str(self.prime_minister))}"
            )
        else:
            minister_value.append(f"{self.bot.mk.pm_term}: -")

        if isinstance(self.lt_prime_minister, discord.Member):
            minister_value.append(
                f"{self.bot.mk.lt_pm_term}: {self.lt_prime_minister.mention}"
            )
        else:
            minister_value.append(f"{self.bot.mk.lt_pm_term}: -")

        embed.add_field(
            name=self.bot.mk.MINISTRY_LEADERSHIP_NAME,
            value="\n".join(minister_value),
            inline=True,
        )

        mk13_min_value = []

        for mk13_min in [
            mk.DemocracivRole.MK13_FINANCE_MIN,
            mk.DemocracivRole.MK13_FOREIGN_MIN,
            mk.DemocracivRole.MK13_DEFENCE_MIN,
            mk.DemocracivRole.MK13_ATTORNEY_GENERAL,
        ]:
            as_member = self._safe_get_member(mk13_min)
            as_role = self.bot.get_democraciv_role(mk13_min)

            if isinstance(as_member, discord.Member):
                mk13_min_value.append(
                    f"{as_role.name}: {as_member.mention} {discord.utils.escape_markdown(str(as_member))}"
                )
            else:
                mk13_min_value.append(f"{as_role.name}: -")

        embed.add_field(
            name="Cabinet of Advisors",
            value="\n".join(mk13_min_value),
            inline=False,
        )

        embed.add_field(
            name=f"{self.bot.mk.COURT_NAME} {self.bot.mk.COURT_JUSTICE_NAME}s ({len(justices) if justices[0] != "-" else 0})",
            value="\n".join(justices),
            inline=False,
        )

        speaker_value = []

        if isinstance(self.speaker, discord.Member):
            speaker_value.append(
                f"{self.bot.mk.speaker_term}: {self.speaker.mention} {discord.utils.escape_markdown(str(self.speaker))}"
            )
        else:
            speaker_value.append(f"{self.bot.mk.speaker_term}: -")

        if isinstance(self.vice_speaker, discord.Member):
            speaker_value.append(
                f"{self.bot.mk.vice_speaker_term}: {self.vice_speaker.mention} {discord.utils.escape_markdown(str(self.vice_speaker))}"
            )
        else:
            speaker_value.append(f"{self.bot.mk.vice_speaker_term}: -")

        mk13_sen_pres = self._safe_get_member(mk.DemocracivRole.MK13_SENATOR_PRESIDING)

        if isinstance(mk13_sen_pres, discord.Member):
            speaker_value.append(
                f"Senator Presiding: {mk13_sen_pres.mention} {discord.utils.escape_markdown(str(mk13_sen_pres))}"
            )
        else:
            speaker_value.append("Senator Presiding: -")

        embed.add_field(
            name=f"{self.bot.mk.LEGISLATURE_CABINET_NAME}",
            value="\n".join(speaker_value),
            inline=False,
        )

        try:
            legislators = self.bot.get_democraciv_role(mk.DemocracivRole.LEGISLATOR)
            legislators = [
                f"{l.mention} {discord.utils.escape_markdown(str(l))}"
                for l in legislators.members
            ] or ["-"]
        except exceptions.RoleNotFoundError:
            legislators = ["-"]

        embed.add_field(
            name=f"Senators ({len(legislators) if legislators[0] != "-" else 0})",
            value="\n".join(legislators),
            inline=False,
        )

        try:
            members_of_gov = self.bot.get_democraciv_role(mk.DemocracivRole.GOVERNMENT)
            members_of_gov = [
                f"{mg.mention} {discord.utils.escape_markdown(str(mg))}"
                for mg in members_of_gov.members
            ] or ["-"]
        except exceptions.RoleNotFoundError:
            members_of_gov = ["-"]

        embed.description = f"There are {len(members_of_gov) if members_of_gov[0] != "-" else "0"} members of government in total."

        return embed

    async def _build_court_overview_embed(self) -> text.SafeEmbed:
        embed = text.SafeEmbed()
        embed.set_author(
            name=f"{self.bot.mk.courts_term} of {self.bot.mk.NATION_FULL_NAME}",
            icon_url=self.bot.mk.NATION_ICON_URL,
        )

        justices = self.get_justices() or ["-"]
        judges = self.get_judges() or ["-"]

        embed.add_field(
            name=f"{self.bot.mk.COURT_NAME} {self.bot.mk.COURT_JUSTICE_NAME}s ({len(justices) if justices[0] != "-" else 0})",
            value="\n".join(justices),
            inline=False,
        )

        if self.bot.mk.COURT_HAS_INFERIOR_COURT:
            embed.add_field(
                name=f"{self.bot.mk.COURT_INFERIOR_NAME} {self.bot.mk.COURT_JUDGE_NAME}s ({len(judges) if judges[0] != "-" else 0})",
                value="\n".join(judges),
                inline=False,
            )

        embed.add_field(
            name="Links",
            value=f"[Constitution]({self.bot.mk.CONSTITUTION})\n[Legal Code]({self.bot.mk.LEGAL_CODE}) *(try [laws.democraciv.com](https://laws.democraciv.com) too!)*",
            inline=False,
        )

        return embed

    async def _build_legislature_info_embeds(
        self, *, slash: bool = False
    ) -> list[text.SafeEmbed]:
        cmd_prefix = "/" if slash else "-"
        help_ref = f"See `/{'senate' if slash else '-help senate'}` for all available commands."

        embed = text.SafeEmbed()
        embed.set_author(
            name="The Commons and the Senate",
            icon_url=self.bot.mk.NATION_ICON_URL,
        )

        com_active_leg_sessions = await self.get_open_leg_sessions(house="commons")
        sen_active_leg_sessions = await self.get_open_leg_sessions(house="senate")

        embed.description = (
            "In MK13, the Legislature consists of two chambers, with the Commons as the Lower House and the Senate as the Upper House. "
            "As such, each house gets their own commands for managing their respective legislative sessions."
        )

        com_session = (
            "No active session."
            if not com_active_leg_sessions
            else "\n".join(
                f"{session.display_name} - {session.status.value}"
                for session in com_active_leg_sessions
            )
        )
        sen_session = (
            "No active session."
            if not sen_active_leg_sessions
            else "\n".join(
                f"{session.display_name} - {session.status.value}"
                for session in sen_active_leg_sessions
            )
        )

        com_cmds = (
            f"- `{cmd_prefix}commons`\n"
            f"- `{cmd_prefix}commons session`\n"
            f"- `{cmd_prefix}commons submit`"
        )
        sen_cmds = (
            f"- `{cmd_prefix}senate`\n"
            f"- `{cmd_prefix}senate session`\n"
            f"- `{cmd_prefix}senate submit`"
        )

        if not slash:
            com_cmds += f"\n\nSee `-help commons` for all available commands."
            sen_cmds += f"\n\nSee `-help senate` for all available commands."

        embed.add_field(
            name="Commons",
            value=f"{com_session}\n\n{com_cmds}",
            inline=True,
        )
        embed.add_field(
            name="Senate",
            value=f"{sen_session}\n\n{sen_cmds}",
            inline=True,
        )

        if slash:
            return [embed]

        embed2 = text.SafeEmbed()
        embed2.set_author(
            name="Additional Commands",
            icon_url=self.bot.mk.NATION_ICON_URL,
        )
        embed2.add_field(
            name="Laws",
            value="- `-laws`\n- `-laws search`\n- `-laws repeal`\n- ...\n- `-help laws`",
            inline=True,
        )
        embed2.add_field(
            name="Bills",
            value="- `-bills`\n- `-bills search`\n- `-bills advanced-search`\n- `-bills sponsor`\n- ...\n- `-help bills`",
            inline=True,
        )
        embed2.add_field(
            name="Motions",
            value="- `-motions`\n- `-motions search`\n- `-motions from <person_or_party>`\n- ...\n- `-help motions`",
            inline=True,
        )

        return [embed, embed2]

    @staticmethod
    def _mk12_bill_from_citizen_has_enough_sponsors(bill) -> bool:
        if bill.sponsors:
            return True
        return False

    async def _build_session_entries(
        self,
        *,
        ctx,
        house: str = "senate",
        session: models.Session,
        sponsor_filter: models.SessionSponsorFilter = None,
    ) -> list[str]:
        entries = []
        sponsors_needed = ""
        bills = [await models.Bill.convert(ctx, b_id) for b_id in session.bills]
        amount_of_all_bills = len(bills)

        if sponsor_filter:
            filter_func, sponsors_needed = sponsor_filter
            bills = list(filter(filter_func, bills))

        if house == "senate":
            pretty_bills = [
                f"* {b.formatted} ({len(b.sponsors)} sponsor{'s' if len(b.sponsors) != 1 else ''}) {':warning:' if not self._mk12_bill_from_citizen_has_enough_sponsors(b) else ''}"
                for b in bills
            ] or ["-"]
        else:
            pretty_bills = [
                f"* {b.formatted} ({len(b.sponsors)} sponsor{'s' if len(b.sponsors) != 1 else ''})"
                for b in bills
            ] or ["-"]

        speaker = session.speaker or context.MockUser()

        if house == "senate":
            presider_label = self.bot.mk.senator_presiding_term
            cmd = self.bot.mk.LEGISLATURE_COMMAND
        else:
            presider_label = "Presiding Speaker"
            cmd = "commons"

        description = (
            f"### {presider_label}\n{speaker.mention}\n"
            f"### Opened\n<t:{int(session.opened_on.timestamp())}:F>\n"
        )

        if session.voting_started_on:
            description = f"{description[:-1]}\n### Voting started\n<t:{int(session.voting_started_on.timestamp())}:F> "

        if session.closed_on:
            description = (
                f"{description[:-1]}\n### Closed\n"
                f"<t:{int(session.closed_on.timestamp())}:F> "
            )

        if session.status is models.SessionStatus.SUBMISSION_PERIOD:
            description = (
                f"{description[:-1]}\n\n-# Bills & Motions can be submitted to this session with "
                f"`{config.BOT_PREFIX}{cmd} submit`. Any old bills from "
                f"previous sessions that failed can be resubmitted to the current submission-period session "
                f"in their origin house with `{config.BOT_PREFIX}bill resubmit`."
            )

        entries.append(description)
        entries.append(f"### Status\n{session.status.value}")

        if session.vote_form:
            entries.append(f"### Voting Form\n{session.vote_form}")

        amount = (
            f"{len(bills)}/{amount_of_all_bills}"
            if sponsor_filter
            else amount_of_all_bills
        )

        entries.append(
            f"### Submitted Bills{'' if not sponsor_filter else f' ({sponsors_needed} sponsors)'}"
            f" ({amount})"
        )

        if not sponsor_filter:
            entries.append(
                f"-# You can filter the list of submitted bills & motions of a session by their amount of sponsors. "
                f"For example, using `{config.BOT_PREFIX}{cmd} session >=2` "
                f"would only show bills & motions that have 2 or more sponsors. See the help page of this command "
                f"for more information.\n"
            )

        entries.extend(pretty_bills)

        if self.bot.mk.LEGISLATURE_MOTIONS_EXIST:
            motions = [(await models.Motion.convert(ctx, m)) for m in session.motions]

            amount_of_all_motions = len(motions)

            if sponsor_filter:
                motions = list(filter(filter_func, motions))

            pretty_motions = [
                f"* {m.formatted} ({len(m.sponsors)} sponsor{'s' if len(m.sponsors) != 1 else ''})"
                for m in motions
            ] or ["-"]
            m_amount = (
                f"{len(motions)}/{amount_of_all_motions}"
                if sponsor_filter
                else amount_of_all_motions
            )
            entries.append(
                f"### Submitted Motions {'' if not sponsor_filter else f' ({sponsors_needed} sponsors)'} ({m_amount})"
            )

            last_motion = pretty_motions.pop()
            last_motion += "\n"
            pretty_motions.append(last_motion)
            entries.extend(pretty_motions)

        return entries

    async def _build_statistics_embed(
        self,
        *,
        ctx=None,
        house: str = "senate",
        target=None,
    ) -> text.SafeEmbed:
        if target is None:
            query = f"""SELECT COUNT(id) FROM legislature_session WHERE house = '{house}'
                       UNION ALL
                       SELECT COUNT(id) FROM bill
                       UNION ALL
                       SELECT COUNT(id) FROM bill WHERE status = $1
                       UNION ALL
                       SELECT COUNT(id) FROM motion"""

            amounts = await self.bot.db.fetch(query, models.BillIsLaw.flag.value)

            submitter = await self.bot.db.fetch("SELECT submitter from bill")
            pretty_top_submitter = self.format_stats(
                record=submitter, record_key="submitter", stats_name="bills"
            )

            speaker = await self.bot.db.fetch(
                f"SELECT speaker from legislature_session WHERE house = '{house}'"
            )
            pretty_top_speaker = self.format_stats(
                record=speaker, record_key="speaker", stats_name="sessions"
            )

            lawmaker = await self.bot.db.fetch(
                "SELECT submitter from bill WHERE status = $1",
                models.BillIsLaw.flag.value,
            )
            pretty_top_lawmaker = self.format_stats(
                record=lawmaker, record_key="submitter", stats_name="laws"
            )

            embed = text.SafeEmbed()

            if house == "senate":
                author_name = (
                    f"Statistics for the {self.bot.mk.NATION_ADJECTIVE} Senate"
                )
                top_speaker_field_name = f"Top {self.bot.mk.senator_presiding_term}s of the {self.bot.mk.LEGISLATURE_NAME}"
            else:
                author_name = "Statistics for the Commons"
                top_speaker_field_name = (
                    f"Top {self.bot.mk.speaker_term}s of the Commons"
                )

            embed.set_author(
                icon_url=self.bot.mk.NATION_ICON_URL,
                name=author_name,
            )

            general_value = (
                f"Sessions: {amounts[0]['count']}\nSubmitted Bills: {amounts[1]['count']}\n"
                f"Submitted Motions: {amounts[3]['count']}\nActive Laws: {amounts[2]['count']}"
            )

            embed.add_field(name="General Statistics", value=general_value)
            embed.add_field(
                name=top_speaker_field_name,
                value=pretty_top_speaker,
                inline=False,
            )
            embed.add_field(
                name="Top Bill Submitters", value=pretty_top_submitter, inline=False
            )
            embed.add_field(
                name="Top Lawmakers", value=pretty_top_lawmaker, inline=False
            )
            return embed

        query = """SELECT COUNT(*) FROM bill WHERE submitter = ANY($1::bigint[])
                               UNION ALL
                               SELECT COUNT(*) FROM bill WHERE submitter = ANY($1::bigint[]) AND status = $2
                               UNION ALL
                               SELECT COUNT(*) FROM motion WHERE submitter = ANY($1::bigint[])
                               UNION ALL
                               SELECT COUNT(id) FROM bill_sponsor WHERE sponsor = ANY($1::bigint[])
                               UNION ALL
                               SELECT COUNT(bill_sponsor.sponsor) FROM bill_sponsor JOIN bill
                               ON bill_sponsor.bill_id = bill.id WHERE bill.submitter = ANY($1::bigint[])"""

        if isinstance(target, converter.PoliticalParty):
            ids = [person.id for person in target.role.members]
            icon_url = await target.get_logo() or self.bot.mk.NATION_ICON_URL or None
            if house == "senate":
                name = (
                    f"Members of {target.role.name} in the "
                    f"{self.bot.mk.NATION_ADJECTIVE} {self.bot.mk.LEGISLATURE_NAME}"
                )
            else:
                name = f"Members of {target.role.name} in the Commons"
        else:
            ids = [target.id]
            icon_url = target.display_avatar.url
            if house == "senate":
                name = (
                    f"{target.display_name} in the {self.bot.mk.NATION_ADJECTIVE} "
                    f"{self.bot.mk.LEGISLATURE_NAME}"
                )
            else:
                name = f"{target.display_name} in the Commons"

        _stats = await self.bot.db.fetch(query, ids, models.BillIsLaw.flag.value)

        embed = text.SafeEmbed()
        embed.set_author(icon_url=icon_url, name=name)
        embed.add_field(name="Bill Submissions", value=_stats[0]["count"], inline=True)
        embed.add_field(
            name="Motion Submissions", value=_stats[2]["count"], inline=True
        )
        embed.add_field(
            name="Amount of Laws written", value=_stats[1]["count"], inline=False
        )
        embed.add_field(
            name="Amount of Bills sponsored", value=_stats[3]["count"], inline=False
        )
        embed.add_field(
            name="Amount of Sponsors for own Bills",
            value=_stats[4]["count"],
            inline=False,
        )
        return embed
