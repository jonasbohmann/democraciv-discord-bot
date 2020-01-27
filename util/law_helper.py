import nltk
import asyncpg
import collections

from bs4 import BeautifulSoup, SoupStrainer

"""
   Several helper functions to query the database for data relevant for legislative sessions.
   
"""


class LawUtils:

    def __init__(self, bot):
        self.bot = bot

        # The natural language processor module nltk used for legislature_tags needs extra data to work
        nltk.download('punkt')
        nltk.download('averaged_perceptron_tagger')

    @staticmethod
    def is_google_doc_link(link: str) -> bool:
        """Checks wether a link is a valid Google Docs or Google Forms link"""

        valid_google_docs_url_strings = ['https://docs.google.com/', 'https://drive.google.com/',
                                         'https://forms.gle/', 'https://goo.gl/forms']

        if len(link) < 15 or not link.startswith(tuple(valid_google_docs_url_strings)):
            return False
        else:
            return True

    async def get_active_leg_session(self):
        active_leg_session_id = await self.bot.db.fetchrow("SELECT id FROM legislature_sessions WHERE is_active = true")

        if active_leg_session_id is None:
            return None
        else:
            return active_leg_session_id['id']

    async def get_status_of_active_leg_session(self):
        active_leg_session_status = await self.bot.db.fetchrow("SELECT status FROM legislature_sessions WHERE"
                                                               " is_active = true")

        if active_leg_session_status is None:
            return None
        else:
            return active_leg_session_status['status']

    async def get_last_leg_session(self):
        last_session = await self.bot.db.fetchrow("SELECT id FROM legislature_sessions WHERE id = "
                                                  "(SELECT MAX(id) FROM legislature_sessions)")

        if last_session is not None:
            return last_session['id']
        else:
            return None

    async def generate_new_bill_id(self) -> int:
        last_bill = await self.bot.db.fetchrow("SELECT id FROM legislature_bills WHERE id = "
                                               "(SELECT MAX(id) FROM legislature_bills)")

        if last_bill is not None:
            last_bill = last_bill['id']
        else:
            last_bill = 0

        return last_bill + 1

    async def generate_new_law_id(self) -> int:
        last_law = await self.bot.db.fetchrow("SELECT law_id FROM legislature_laws WHERE law_id = "
                                              "(SELECT MAX(law_id) FROM legislature_laws)")

        if last_law is not None:
            last_law = last_law['law_id']
        else:
            last_law = 0

        return last_law + 1

    async def generate_new_motion_id(self) -> int:
        last_motion = await self.bot.db.fetchrow("SELECT id FROM legislature_motions WHERE id = "
                                                 "(SELECT MAX(id) FROM legislature_motions)")

        if last_motion is not None:
            last_motion = last_motion['id']
        else:
            last_motion = 0

        return last_motion + 1

    async def get_google_docs_title(self, link: str):
        """Gets title of a Google Docs document"""

        try:
            async with self.bot.session.get(link) as response:
                text = await response.read()

            strainer = SoupStrainer(property="og:title")  # Only parse the title property to save time
            soup = BeautifulSoup(text, "lxml", parse_only=strainer)  # Use lxml parser to speed things up

            bill_title = soup.find("meta")['content']  # Get title of Google Docs website

            if bill_title.endswith(' - Google Docs'):
                bill_title = bill_title[:-14]

            soup.decompose()  # Garbage collection

            return bill_title

        except Exception:
            return None

    async def get_google_docs_description(self, link: str):
        """Gets content of 'og:description' tag from HTML of a Google Docs page.

            That content includes the document's title and the first few paragraphs of text."""

        try:
            async with self.bot.session.get(link) as response:
                text = await response.read()

            strainer = SoupStrainer(property="og:description")
            soup = BeautifulSoup(text, "lxml", parse_only=strainer)

            bill_description = soup.find("meta")['content']

            # If the description is long enough, Google adds a ... to the end of it
            if bill_description.endswith('...'):
                bill_description = bill_description[:-3]

            soup.decompose()  # Garbage collection

            return bill_description

        except Exception:
            return None

    @staticmethod
    def generate_law_tags(google_docs_description: str, author_description: str) -> list:
        """Generates tags from all nouns of submitter-provided description and the Google Docs description"""

        # Function to check if token is noun
        is_noun = lambda pos: pos[:2] == 'NN'

        # Tokenize both descriptions
        tokenized_docs_description = nltk.word_tokenize(google_docs_description)
        tokenized_author_description = nltk.word_tokenize(author_description)

        # Add all nouns to list
        tags = [word for (word, pos) in nltk.pos_tag(tokenized_docs_description) +
                nltk.pos_tag(tokenized_author_description) if is_noun(pos)]

        # Eliminate duplicate tags
        tags = list(set(tags))

        return tags

    async def pass_into_law(self, ctx, bill_id: int, bill_details: asyncpg.Record) -> bool:
        """Marks a Bill as passed and creates new Law from that Bill."""

        await self.bot.db.execute("UPDATE legislature_bills SET voted_on_by_ministry = true, has_passed_ministry = "
                                  "true WHERE id = $1", bill_id)

        # This could've been solved with SQL 'AUTO INCREMENT' but I didn't know that that existed
        _law_id = await self.bot.laws.generate_new_law_id()

        try:
            await self.bot.db.execute("INSERT INTO legislature_laws (bill_id, law_id, description) VALUES"
                                      "($1, $2, $3)", bill_id, _law_id, bill_details['description'])
        except asyncpg.UniqueViolationError:
            await ctx.send(f":x: This bill is already law!")
            return False

        # The bot takes the submitter-provided description (from the -legislature submit command) *and* the description
        # from Google Docs (og:description property in HTML, usually the title of the Google Doc and the first
        # few sentence's of content.) and tokenizes those with nltk. Then, every noun from both descriptions is saved
        # into the legislature_tags table with the corresponding law_id.

        _google_docs_description = await self.bot.laws.get_google_docs_description(bill_details['link'])
        _tags = await self.bot.loop.run_in_executor(None, self.bot.laws.generate_law_tags, _google_docs_description,
                                                    bill_details['description'])

        for tag in _tags:
            await self.bot.db.execute("INSERT INTO legislature_tags (id, tag) VALUES ($1, $2)", _law_id,
                                      tag.lower())

        return True

    @staticmethod
    def sort_dict_by_value(to_be_sorted: dict) -> dict:
        """Sorts a dict by values in reverse order (i.e.: bigger number -> top of the dict)"""

        to_be_sorted = {k: v for k, v in sorted(to_be_sorted.items(),
                                                key=lambda item: item[1], reverse=True)}

        return to_be_sorted

    @staticmethod
    def count_rows_from_db_record(record: asyncpg.Record, record_key: str) -> dict:
        """Converts a database asyncp.Record into a dict with Record keys as keys and their
         amount of occurrence as value"""

        record_as_list = []

        for r in record:
            record_as_list.append(r[record_key])

        counter = collections.Counter(record_as_list)
        return dict(counter)

    def get_pretty_stats(self, to_be_pretty: dict, stats_name: str) -> str:
        """Prettifies the dicts used in generate_leg_statistics() to strings"""

        pretty = f""
        i = 1

        for key, value in to_be_pretty.items():
            if self.bot.get_user(key) is not None:
                if i > 5:
                    break

                if value == 1:
                    # Singular stats_name

                    pretty += f"{i}. {self.bot.get_user(key).mention} with {value} {stats_name[:-1]}\n"
                else:
                    # Plural stats_name
                    pretty += f"{i}. {self.bot.get_user(key).mention} with {value} {stats_name}\n"
                i += 1

            else:
                continue

        return pretty

    async def generate_leg_statistics(self) -> list:
        """Generates statistics for the -legislature stats command"""

        # General total amount of things
        amount_of_sessions = (await self.bot.db.fetchrow("SELECT COUNT(id) FROM legislature_sessions"))['count']
        amount_of_bills = (await self.bot.db.fetchrow("SELECT COUNT(id) FROM legislature_bills"))['count']
        amount_of_laws = (await self.bot.db.fetchrow("SELECT COUNT(law_id) FROM legislature_laws"))['count']
        amount_of_motions = (await self.bot.db.fetchrow("SELECT COUNT(id) FROM legislature_motions"))['count']

        # Sorted statistics by discord.Member
        amount_of_bills_by_submitter = self.count_rows_from_db_record(await self.bot.db.fetch("SELECT submitter FROM "
                                                                                              "legislature_bills"),
                                                                      'submitter')
        amount_of_sessions_by_speaker = self.count_rows_from_db_record(await self.bot.db.fetch("SELECT speaker FROM "
                                                                                               "legislature_sessions"),
                                                                       'speaker')
        amount_of_laws_by_submitter = self.count_rows_from_db_record(await self.bot.db.fetch("SELECT submitter FROM "
                                                                                             "legislature_bills WHERE"
                                                                                             " has_passed_leg = true "
                                                                                             "AND has_passed_ministry "
                                                                                             "= true"), 'submitter')

        # Prettified sorted statistics by discord.Member
        # TODO - Limit to Top 5
        pretty_top_submitter = self.get_pretty_stats(self.sort_dict_by_value(amount_of_bills_by_submitter), 'bills')

        pretty_top_speaker = self.get_pretty_stats(self.sort_dict_by_value(amount_of_sessions_by_speaker), 'sessions')

        pretty_top_lawmaker = self.get_pretty_stats(self.sort_dict_by_value(amount_of_laws_by_submitter), 'laws')

        return [amount_of_sessions, amount_of_bills, amount_of_laws, amount_of_motions,
                pretty_top_submitter, pretty_top_speaker, pretty_top_lawmaker]

    async def post_to_hastebin(self, text: str):
        """Post text to hastebin.com"""

        async with self.bot.session.post("https://hastebin.com/documents", data=text) as response:
            data = await response.json()
            key = data['key']

        return f"https://hastebin.com/{key}"

    async def search_law_by_name(self, name: str) -> list:
        """Search for laws by their name, returns list with prettified strings of found laws"""
        bills = await self.bot.db.fetch("SELECT * FROM legislature_bills WHERE bill_name % $1", name.lower())

        found_bills = []

        for bill in bills:

            # Only find bills that are laws, i.e. that have passed at least the Legislature
            if bill['has_passed_leg']:

                # Only find bills that are either not vetoable, or that also passed the Ministry if they are vetoable
                if bill['is_vetoable'] and bill['has_passed_ministry']:
                    _id = (await self.bot.db.fetchrow("SELECT law_id FROM legislature_laws WHERE bill_id = $1",
                                                      bill['id']))['law_id']
                    found_bills.append(f"Law #{_id} - [{bill['bill_name']}]({bill['link']})")
                elif not bill['is_vetoable']:
                    _id = (await self.bot.db.fetchrow("SELECT law_id FROM legislature_laws WHERE bill_id = $1",
                                                      bill['id']))['law_id']
                    found_bills.append(f"Law #{_id} - [{bill['bill_name']}]({bill['link']})")

                else:
                    continue

            else:
                continue

        return found_bills

    async def search_law_by_tag(self, tag: str) -> list:
        """Search for laws by their tag(s), returns list with prettified strings of found laws"""

        # Once a bill is passed into law, the bot automatically generates tags for it to allow for easier and faster
        # searching.

        # The bot takes the submitter-provided description (from the -legislature submit command) *and* the description
        # from Google Docs (og:description property in HTML, usually the title of the Google Doc and the first
        # few sentence's of content.) and tokenizes those with nltk. Then, every noun from both descriptions is saved
        # into the legislature_tags table with the corresponding law_id.

        found_bills = await self.bot.db.fetch("SELECT id FROM legislature_tags WHERE tag % $1", tag.lower())

        bills = []

        for bill in found_bills:
            bills.append(bill['id'])

        bills = list(set(bills))

        pretty_laws = []

        for bill in bills:
            bill_id = (await self.bot.db.fetchrow("SELECT bill_id FROM legislature_laws WHERE law_id = $1", bill))[
                'bill_id']
            details = await self.bot.db.fetchrow("SELECT link, bill_name FROM legislature_bills WHERE id = $1",
                                                 bill_id)
            pretty_laws.append(f"Law #{bill} - [{details['bill_name']}]({details['link']})")

        return pretty_laws
