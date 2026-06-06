import collections
import datetime
import re
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


class SessionChoiceNoneButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Skip this for now. Bills will be added to the next new non-emergency session.",
            style=(discord.ButtonStyle.secondary),
        )

    async def callback(self, interaction):
        await interaction.response.defer()
        self.view.result = None
        self.view.stop()


class SessionChooseView(text.PromptView):
    def __init__(
        self,
        ctx,
        *,
        sessions: typing.Sequence[models.Session],
        allow_none: bool = False,
    ):
        super().__init__(ctx)
        for session in sessions:
            self.add_item(SessionChoiceButton(session))

        if allow_none:
            self.add_item(SessionChoiceNoneButton())


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


_BILL_AMENDMENT_SPLIT_RE = re.compile(r"[\s,]+")
_MARKDOWN_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_MARKDOWN_HTML_TAG_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9-]*(?:\s[^>\n]*)?\s*/?>")
_MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*\S)\s*$")
_MARKDOWN_RULE_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_MARKDOWN_TABLE_SEPARATOR_RE = re.compile(
    r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$"
)


def _split_markdown_table_row(row: str) -> typing.List[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def _format_markdown_table_for_discord(rows: typing.Sequence[str]) -> str:
    parsed_rows = [_split_markdown_table_row(row) for row in rows]
    max_columns = max(len(row) for row in parsed_rows)

    for row in parsed_rows:
        row.extend([""] * (max_columns - len(row)))

    widths = [
        max(len(row[column]) for row in parsed_rows) for column in range(max_columns)
    ]

    formatted_rows = [
        " | ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)).rstrip()
        for row in parsed_rows
    ]

    return "```text\n" + "\n".join(formatted_rows) + "\n```"


def _chunk_string(value: str, *, size: int) -> typing.List[str]:
    if not value:
        return [""]

    return [value[index : index + size] for index in range(0, len(value), size)]


def _split_large_markdown_block(block: str, *, max_chars: int) -> typing.List[str]:
    if block.startswith("```") and block.endswith("```"):
        lines = block.splitlines()
        opening = lines[0]
        closing = lines[-1]
        body_lines = lines[1:-1]
        body_limit = max(1, max_chars - len(opening) - len(closing) - 2)
        pages = []
        current_lines = []
        current_size = len(opening) + len(closing) + 2

        for line in body_lines or [""]:
            for chunk in _chunk_string(line, size=body_limit):
                chunk_size = len(chunk) + (1 if current_lines else 0)
                if current_lines and current_size + chunk_size > max_chars:
                    pages.append(
                        f"{opening}\n" + "\n".join(current_lines) + f"\n{closing}"
                    )
                    current_lines = [chunk]
                    current_size = len(opening) + len(closing) + 2 + len(chunk)
                else:
                    current_lines.append(chunk)
                    current_size += chunk_size

        if current_lines:
            pages.append(f"{opening}\n" + "\n".join(current_lines) + f"\n{closing}")

        return pages

    try:
        return text.split_string_into_multiple(block, max_chars)
    except RuntimeError:
        return _chunk_string(block, size=max_chars)


def _split_markdown_into_blocks(markdown: str) -> typing.List[str]:
    blocks = []
    current = []
    in_code_fence = False

    for line in markdown.splitlines():
        if line.lstrip().startswith("```"):
            current.append(line)
            in_code_fence = not in_code_fence
            continue

        if not in_code_fence and not line.strip():
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            continue

        current.append(line)

    if current:
        blocks.append("\n".join(current).strip())

    return [block for block in blocks if block]


def _paginate_markdown_for_discord(
    markdown: str, *, max_chars: int = 1800
) -> typing.List[str]:
    blocks = _split_markdown_into_blocks(markdown)
    pages = []
    current = ""

    for block in blocks or ["*No stored text available.*"]:
        candidate = block if not current else f"{current}\n\n{block}"

        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            pages.append(current)
            current = ""

        if len(block) <= max_chars:
            current = block
            continue

        pages.extend(_split_large_markdown_block(block, max_chars=max_chars))

    if current:
        pages.append(current)

    return pages


def _normalize_markdown_for_discord(markdown: str) -> str:
    value = (markdown or "").replace("\r\n", "\n").replace("\r", "\n")
    value = _MARKDOWN_HTML_COMMENT_RE.sub("", value)
    value = _MARKDOWN_IMAGE_RE.sub(
        lambda match: f"[Image: {(match.group(1).strip() or 'View image')}]({match.group(2).strip()})",
        value,
    )
    value = _MARKDOWN_HTML_TAG_RE.sub("", value)

    lines = value.splitlines()
    normalized = []
    index = 0
    in_code_fence = False

    while index < len(lines):
        line = lines[index].rstrip()
        stripped = line.strip()

        if line.lstrip().startswith("```"):
            normalized.append(line)
            in_code_fence = not in_code_fence
            index += 1
            continue

        if in_code_fence:
            normalized.append(line)
            index += 1
            continue

        if (
            stripped
            and "|" in stripped
            and index + 1 < len(lines)
            and _MARKDOWN_TABLE_SEPARATOR_RE.match(lines[index + 1].strip())
        ):
            table_lines = [line]
            index += 2

            while index < len(lines):
                next_line = lines[index].rstrip()
                if not next_line.strip() or "|" not in next_line:
                    break

                table_lines.append(next_line)
                index += 1

            normalized.append(_format_markdown_table_for_discord(table_lines))
            continue

        heading = _MARKDOWN_HEADING_RE.match(line)
        if heading:
            normalized.append(f"**{heading.group(2).strip()}**")
            index += 1
            continue

        if _MARKDOWN_RULE_RE.match(stripped):
            normalized.append("────────")
            index += 1
            continue

        normalized.append(line)
        index += 1

    return re.sub(r"\n{3,}", "\n\n", "\n".join(normalized)).strip()


def make_bill_amendments_input(
    *,
    default: str = None,
    description: str = None,
    placeholder: str = "12, 34, 37",
    required: bool = False,
):
    return discord.ui.Label(
        text="Does this amend any existing bill or bills?",
        description=description
        or "Optional. Enter existing bill IDs separated by commas, spaces, or new lines.",
        component=discord.ui.TextInput(
            style=discord.TextStyle.long,
            default=default,
            placeholder=placeholder,
            required=required,
            max_length=500,
        ),
    )


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

    def _related_bills_field_value(self, related_bills: typing.Sequence[models.RelatedBillSummary]) -> str:
        lines = []
        current_length = 0

        for bill in related_bills:
            line = bill.formatted
            added_length = len(line) + (1 if lines else 0)

            if current_length + added_length > 1020:
                lines.append("...")
                break

            lines.append(line)
            current_length += added_length

        return "\n".join(lines)

    def _add_bill_amendment_fields(self, embed: discord.Embed, bill: models.Bill):
        if bill.amends:
            embed.add_field(
                name="Amends",
                value=self._related_bills_field_value(bill.amends),
                inline=False,
            )

        if bill.amended_by:
            embed.add_field(
                name="Amended By",
                value=self._related_bills_field_value(bill.amended_by),
                inline=False,
            )

    def _build_legal_detail_embed(
        self,
        obj: typing.Union[models.Bill, models.Motion, models.Law],
    ) -> text.SafeEmbed:
        embed = text.SafeEmbed(
            title=f"{obj.name} (#{obj.id})",
            description=obj.description or "*No summary provided.*",
            url=obj.link,
        )

        if obj.submitter is not None:
            embed.set_author(
                name=f"Submitted by {obj.submitter.name}",
                icon_url=obj.submitter.display_avatar.url,
            )
            submitted_by_value = f"{obj.submitter.mention} {obj.submitter}"
        else:
            submitted_by_value = "*Unknown Person*"

        embed.add_field(name="Submitter", value=submitted_by_value, inline=True)

        if isinstance(obj, models.Bill) and not isinstance(obj, models.Law):
            if obj.session.house in models.HOUSE_NAMES:
                embed.add_field(
                    name="Orig. in Chamber", value=obj.origin_house_name, inline=True
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
                    value=f"<t:{int(obj.executive_deadline_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:R> ",
                    inline=True,
                )

            if obj.sponsors:
                fmt_sponsors = "\n".join(
                    f"{sponsor.mention} {sponsor}" for sponsor in obj.sponsors
                )
                embed.add_field(name="Sponsors", value=fmt_sponsors, inline=False)

        if isinstance(obj, models.Bill):
            self._add_bill_amendment_fields(embed, obj)

        if not isinstance(obj, models.Motion):
            history = [
                f"* <t:{int(entry.date.timestamp())}:D> - {entry.note if entry.note else entry.after}"
                for entry in obj.history[:10]
            ]

            if history:
                embed.add_field(name="History", value="\n".join(history), inline=False)

            if not isinstance(obj, models.Law) and obj.status.is_law:
                embed.set_footer(text="This is an active law.")
        elif obj.sponsors:
            fmt_sponsors = "\n".join(
                f"{sponsor.mention} {sponsor}" for sponsor in obj.sponsors
            )
            embed.add_field(name="Sponsors", value=fmt_sponsors, inline=False)

        return embed

    async def _detail_view(
        self,
        ctx: context.CustomContext,
        *,
        obj: typing.Union[models.Bill, models.Motion, models.Law],
    ):
        embed = self._build_legal_detail_embed(obj)

        if not isinstance(obj, models.Motion):
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
            await ctx.send(
                f"-# {config.HINT} Check out [laws.democraciv.com](<https://laws.democraciv.com/{obj.model.lower()}/{obj.id}>) as well!"
            )
            await ctx.send(embed=embed)

    async def _show_bill_text(self, ctx, bill: models.Bill, *, ephemeral_webhook=None):
        leader_term = self.get_primary_leader_term_for_house(
            getattr(getattr(bill, "session", None), "house", None)
        )
        document_kind = bill.model.lower()
        document_label = bill.model
        document_text = (
            _normalize_markdown_for_discord(bill.markdown)
            if bill.markdown
            else bill.content
        )
        entries = _paginate_markdown_for_discord(
            f"[Link to the Google Docs document of this {document_label}]({bill.link})\n"
            f"*Am I showing you outdated or wrong text? Tell the {leader_term} to synchronize this text "
            f"with the Google Docs text of this document with `{config.BOT_PREFIX}bill synchronize {bill.id}`.*\n\n"
            f"{document_text or '*No stored text available.*'}"
        )
        pages = paginator.SimplePages(
            entries=entries,
            icon=self.bot.mk.NATION_ICON_URL,
            author=f"{bill.name} (#{bill.id})",
            ephemeral_webhook=ephemeral_webhook,
            per_page=1,
        )
        await ctx.send(
            f"-# {config.HINT} Check out [laws.democraciv.com](<https://laws.democraciv.com/{document_kind}/{bill.id}>) as well!"
        )
        await pages.start(ctx)

    @staticmethod
    def _bill_amendment_history_note(
        related_bills: typing.Sequence[models.RelatedBillSummary],
    ) -> str:
        if not related_bills:
            return "Cleared amendment links."

        ids = ", ".join(f"#{bill.id}" for bill in related_bills)
        noun = "bill" if len(related_bills) == 1 else "bills"
        return f"This bill is an amendment to {noun} {ids}."

    @staticmethod
    def format_bill_amendment_ids(
        related_bills: typing.Sequence[models.RelatedBillSummary],
    ) -> str:
        return ", ".join(str(bill.id) for bill in related_bills)

    @staticmethod
    def parse_bill_amendment_ids(raw_value: str) -> typing.List[int]:
        value = (raw_value or "").strip()
        if not value:
            return []

        tokens = [
            token.removeprefix("#")
            for token in _BILL_AMENDMENT_SPLIT_RE.split(value)
            if token
        ]
        amendment_ids = []
        seen = set()
        duplicate_ids = []
        invalid_tokens = []

        for token in tokens:
            try:
                bill_id = int(token)
            except ValueError:
                invalid_tokens.append(token)
                continue

            if bill_id <= 0:
                invalid_tokens.append(token)
                continue

            if bill_id in seen:
                duplicate_ids.append(bill_id)
                continue

            seen.add(bill_id)
            amendment_ids.append(bill_id)

        if invalid_tokens:
            formatted = ", ".join(f"`{token}`" for token in invalid_tokens)
            raise exceptions.InvalidUserInputError(
                f"{config.NO} Amendment bill IDs must be numbers. Invalid values: {formatted}."
            )

        if duplicate_ids:
            formatted = ", ".join(f"#{bill_id}" for bill_id in duplicate_ids)
            raise exceptions.InvalidUserInputError(
                f"{config.NO} You listed the same amended bill more than once: {formatted}."
            )

        return amendment_ids

    async def resolve_bill_amendment_targets(
        self,
        amendment_ids: typing.Sequence[int],
        *,
        bill_id: int,
        connection=None,
    ) -> typing.List[models.RelatedBillSummary]:
        if bill_id in amendment_ids:
            raise exceptions.InvalidUserInputError(
                f"{config.NO} A bill cannot amend itself."
            )

        if not amendment_ids:
            return []

        con = connection or self.bot.db
        rows = await con.fetch(
            "SELECT bill.id, bill.name, bill.link, bill.status, legislature_session.house, "
            "bill.origin_house, bill.is_procedure, bill.is_vetoable "
            "FROM bill LEFT JOIN legislature_session ON bill.leg_session = legislature_session.id "
            "WHERE bill.id = ANY($1::int[])",
            amendment_ids,
        )
        found = {row["id"]: models.RelatedBillSummary(**dict(row)) for row in rows}
        missing_ids = [
            candidate for candidate in amendment_ids if candidate not in found
        ]

        if missing_ids:
            formatted = ", ".join(f"#{bill_id}" for bill_id in missing_ids)
            raise exceptions.InvalidUserInputError(
                f"{config.NO} I couldn't find the amended bill(s) {formatted}."
            )

        return [found[candidate] for candidate in amendment_ids]

    async def replace_bill_amendments(
        self,
        *,
        bill: models.Bill,
        amendment_ids: typing.Sequence[int],
        connection=None,
    ) -> typing.List[models.RelatedBillSummary]:
        con = connection or self.bot.db
        related_bills = await self.resolve_bill_amendment_targets(
            amendment_ids,
            bill_id=bill.id,
            connection=con,
        )
        await con.execute(
            "DELETE FROM bill_amendment WHERE amending_bill_id = $1",
            bill.id,
        )

        if related_bills:
            await con.executemany(
                "INSERT INTO bill_amendment (amending_bill_id, amended_bill_id) "
                "VALUES ($1, $2) ON CONFLICT DO NOTHING",
                [(bill.id, related_bill.id) for related_bill in related_bills],
            )

        bill.amends = list(related_bills)
        return bill.amends

    async def update_bill_amendments(
        self,
        *,
        bill: models.Bill,
        amendment_ids: typing.Sequence[int],
    ) -> bool:
        if list(amendment_ids) == [related_bill.id for related_bill in bill.amends]:
            return False

        async with self.bot.db.acquire() as con:
            async with con.transaction():
                related_bills = await self.replace_bill_amendments(
                    bill=bill,
                    amendment_ids=amendment_ids,
                    connection=con,
                )

        await bill.status.log_history(
            old_status=bill.status.flag,
            new_status=bill.status.flag,
            note=self._bill_amendment_history_note(related_bills),
        )
        return True

    def build_bill_submission_embed(
        self,
        ctx,
        *,
        session: models.Session,
        bill: models.Bill,
    ) -> text.SafeEmbed:
        house_name = models.display_house_name(bill.origin_house)
        embed = text.SafeEmbed(
            title=f"{bill.name} (#{bill.id})",
            url=bill.link,
            description=f"Hey! A new **bill** was just submitted to {session.display_name}.",
        )
        embed.add_field(
            name="Type",
            value=f"{house_name} Procedure" if bill.is_procedure else "Bill",
            inline=False,
        )
        embed.add_field(name="Description", value=bill.description, inline=False)
        embed.add_field(
            name="Author", value=f"{ctx.author.mention} {ctx.author}", inline=False
        )
        embed.add_field(name="Google Docs Document", value=bill.link, inline=False)
        if bill.amends:
            embed.add_field(
                name="Amends",
                value=self._related_bills_field_value(bill.amends),
                inline=False,
            )
        embed.add_field(
            name="Exact Time of Submission",
            value=f"<t:{int(discord.utils.utcnow().timestamp())}:F>",
            inline=False,
        )
        embed.set_author(
            icon_url=ctx.author_icon,
            name=f"Submitted by {ctx.author.display_name}",
        )
        return embed

    async def create_submitted_bill(
        self,
        *,
        ctx,
        session: models.Session,
        house: str,
        google_docs_url: str,
        bill_description: str,
        is_procedure: bool,
        amendment_input: str = "",
    ) -> models.Bill:
        if not google_docs_url:
            raise exceptions.InvalidUserInputError(
                f"{config.NO} Missing Google Docs URL."
            )

        bill_description = bill_description or "*No summary provided by submitter.*"
        bill = models.Bill(
            bot=self.bot,
            link=google_docs_url,
            submitter_description=bill_description,
        )
        document = await bill.fetch_name_and_keywords()

        if not document.name:
            raise exceptions.InvalidUserInputError(
                f"{config.NO} Something went wrong. Are you sure the Google Docs document is public?\n"
                f"{config.HINT} Word (.docx) documents on Google Docs are not supported."
            )

        amendment_ids = self.parse_bill_amendment_ids(amendment_input)

        async with self.bot.db.acquire() as con:
            async with con.transaction():
                bill_id = await con.fetchval(
                    "INSERT INTO bill (leg_session, name, link, submitter, is_vetoable, "
                    "is_procedure, submitter_description, content, markdown, html, "
                    "html_zip, pdf, origin_house) VALUES ($1, $2, $3, $4, $5, $6, $7, "
                    "$8, $9, $10, $11, $12, $13) RETURNING id",
                    session.id,
                    document.name,
                    google_docs_url,
                    ctx.author.id,
                    not is_procedure,
                    is_procedure,
                    bill_description,
                    document.content,
                    document.markdown,
                    document.html,
                    document.html_zip,
                    document.pdf,
                    house,
                )
                bill.id = bill_id
                bill.name = document.name
                bill.content = document.content
                bill.markdown = document.markdown
                bill.html = document.html
                bill.html_zip = document.html_zip
                bill.pdf = document.pdf
                bill.description = bill_description
                bill.is_vetoable = not is_procedure
                bill.is_procedure = is_procedure
                bill.origin_house = house
                bill.session = session
                bill.submitter_id = ctx.author.id

                await con.execute(
                    "INSERT INTO bill_session (bill_id, leg_session) VALUES ($1, $2) "
                    "ON CONFLICT DO NOTHING",
                    bill_id,
                    session.id,
                )
                await bill.status.log_history(
                    old_status=models.BillSubmitted.flag,
                    new_status=models.BillSubmitted.flag,
                    note=f"Submitted to {session.display_name}",
                    connection=con,
                )

                if document.keywords:
                    await con.executemany(
                        "INSERT INTO bill_lookup_tag (bill_id, tag) VALUES ($1, $2) "
                        "ON CONFLICT DO NOTHING",
                        [(bill_id, tag) for tag in document.keywords],
                    )

                related_bills = await self.replace_bill_amendments(
                    bill=bill,
                    amendment_ids=amendment_ids,
                    connection=con,
                )
                if related_bills:
                    await bill.status.log_history(
                        old_status=bill.status.flag,
                        new_status=bill.status.flag,
                        note=self._bill_amendment_history_note(related_bills),
                        connection=con,
                    )

        await self.bot.api_request(
            "POST", "document/add", silent=True, json={"id": bill.id, "type": "bill"}
        )
        return bill

    async def _synchronize_bill(self, bill: models.Bill) -> bool:
        try:
            document = await bill.fetch_name_and_keywords()
            if not document.name:
                return False

            await self.bot.db.execute(
                "UPDATE bill SET name = $1, content = $2, markdown = $3, html = $4, "
                "html_zip = $5, pdf = $6 WHERE id = $7",
                document.name,
                document.content,
                document.markdown,
                document.html,
                document.html_zip,
                document.pdf,
                bill.id,
            )
            await self.bot.db.execute(
                "DELETE FROM bill_lookup_tag WHERE bill_id = $1", bill.id
            )
            if document.keywords:
                await self.bot.db.executemany(
                    "INSERT INTO bill_lookup_tag (bill_id, tag) VALUES ($1, $2) "
                    "ON CONFLICT DO NOTHING",
                    [(bill.id, tag) for tag in document.keywords],
                )
            await self.bot.api_request(
                "POST",
                "document/update",
                silent=True,
                json={"id": bill.id, "type": "bill"},
            )
            return True
        except Exception:
            return False

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
        allow_none: bool = False,
    ) -> typing.Optional[models.Session]:

        view = SessionChooseView(ctx, sessions=sessions, allow_none=allow_none)
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
                session_value = "There currently is no open session in the Senate."
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

        if is_senate:
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
                    f"[Senate Docket/Worksheet]({self.bot.mk.LEGISLATURE_DOCKET})\n"
                    f"[Senate Procedures]({self.bot.mk.LEGISLATURE_PROCEDURES})"
                ),
                inline=False,
            )
        else:
            embed.add_field(
                name="Links",
                value=(
                    f"[Constitution]({self.bot.mk.CONSTITUTION})\n"
                    f"[Legal Code]({self.bot.mk.LEGAL_CODE}) "
                    "*(try [laws.democraciv.com](https://laws.democraciv.com) too!)*\n"
                    f"[Commons Docket/Worksheet](https://docs.google.com/spreadsheets/d/1tNj-iI23T2eFpV4jbEQQKl-VIrO87etI9xYp5vSG_qA)\n"
                    f"[Commons Procedures](https://docs.google.com/document/d/1iLwNrdtjnw24kNz2-T_nsiKaKwqZmJKmntTlC4Fiaqk)"
                ),
                inline=False,
            )

        session_label = (
            "Current Commons Session" if not is_senate else "Current Senate Session"
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

    def _build_government_overview_embed(self) -> text.SafeEmbed:
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

    def _build_court_overview_embed(self) -> text.SafeEmbed:
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
                f"* {b.formatted} ({len(b.sponsors)} sponsor{'s' if len(b.sponsors) != 1 else ''})"
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
        house_name = models.display_house_name(house)

        if target is None:
            query = (
                f"SELECT COUNT(id) FROM legislature_session WHERE house = $1 "
                "UNION ALL "
                f"SELECT COUNT(id) FROM bill WHERE origin_house = $1 "
                "UNION ALL "
                f"SELECT COUNT(id) FROM bill WHERE status = $2 AND origin_house = $1 "
                "UNION ALL "
                "SELECT COUNT(m.id) FROM motion m "
                "JOIN legislature_session ls ON m.leg_session = ls.id "
                f"WHERE ls.house = $1"
            )

            amounts = await self.bot.db.fetch(
                query, house, models.BillIsLaw.flag.value
            )

            submitter = await self.bot.db.fetch(
                "SELECT submitter FROM bill WHERE origin_house = $1", house
            )
            pretty_top_submitter = self.format_stats(
                record=submitter, record_key="submitter", stats_name="bills"
            )

            speaker = await self.bot.db.fetch(
                "SELECT speaker FROM legislature_session WHERE house = $1", house
            )
            pretty_top_speaker = self.format_stats(
                record=speaker, record_key="speaker", stats_name="sessions"
            )

            lawmaker = await self.bot.db.fetch(
                "SELECT submitter FROM bill WHERE status = $1 AND origin_house = $2",
                models.BillIsLaw.flag.value,
                house,
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
                f"Sessions: {amounts[0]['count']}\n"
                f"Submitted Bills from the {house_name}: {amounts[1]['count']}\n"
                f"Submitted Motions in {house_name} Sessions: {amounts[3]['count']}\n"
                f"Active Laws Originating in the {house_name}: {amounts[2]['count']}"
            )

            embed.add_field(name="General Statistics", value=general_value)
            embed.add_field(
                name=top_speaker_field_name,
                value=pretty_top_speaker,
                inline=False,
            )
            embed.add_field(
                name=f"Top Bill Submitters in the {house_name}",
                value=pretty_top_submitter,
                inline=False,
            )
            embed.add_field(
                name=f"Top Lawmakers Originating in the {house_name}",
                value=pretty_top_lawmaker,
                inline=False,
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
