import datetime
import typing
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

        if isinstance(obj, models.Bill) and not isinstance(obj, models.Law):
            if obj.session.house in models.HOUSE_NAMES:
                embed.add_field(
                    name="Origin House", value=obj.origin_house_name, inline=True
                )
                embed.add_field(name="Type", value=obj.type_name, inline=True)
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
                    value=f"<t:{int(obj.executive_deadline_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:F>",
                    inline=True,
                )

            if obj.sponsors:
                fmt_sponsors = "\n".join(
                    [f"{sponsor.mention} {sponsor}" for sponsor in obj.sponsors]
                )
                embed.add_field(name="Sponsors", value=fmt_sponsors, inline=False)

        if not isinstance(obj, models.Motion):
            history = [
                f"* <t:{int(entry.date.timestamp())}:D> - {entry.note if entry.note else entry.after}"
                for entry in obj.history[:10]
            ]

            if history:
                embed.add_field(name="History", value="\n".join(history), inline=False)

            if not isinstance(obj, models.Law) and obj.status.is_law:
                embed.set_footer(text="This is an active law.")

            view = ReadDocumentView(ctx=ctx)
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

    async def get_active_leg_session(
        self, house=None
    ) -> typing.Optional[models.Session]:
        if house is not None:
            session_id = await self.bot.db.fetchval(
                "SELECT id FROM legislature_session WHERE status != 'Closed' AND house = $1",
                house,
            )
        else:
            session_id = await self.bot.db.fetchval(
                "SELECT id FROM legislature_session WHERE status != 'Closed'"
            )

        if session_id is not None:
            return await models.Session.convert(
                context.MockContext(self.bot), session_id
            )

    async def get_last_leg_session(self, house=None) -> typing.Optional[models.Session]:
        if house is not None:
            session_id = await self.bot.db.fetchval(
                "SELECT MAX(id) FROM legislature_session WHERE house = $1", house
            )
        else:
            session_id = await self.bot.db.fetchval(
                "SELECT MAX(id) FROM legislature_session"
            )

        if session_id is not None:
            return await models.Session.convert(
                context.MockContext(self.bot), session_id
            )

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
