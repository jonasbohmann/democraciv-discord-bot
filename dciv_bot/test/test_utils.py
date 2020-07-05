import discord
import unittest

from dciv_bot.config import config
from dciv_bot.util.utils import EmbedUtils


class TestEmbedUtils(unittest.TestCase):

    def setUp(self):
        self.embed_utils = EmbedUtils()
        self.embed = discord.Embed(title="Test Embed", description="Test Description", colour=config.BOT_EMBED_COLOUR)

    def test_embed_builder_title(self):
        self.assertEqual(self.embed_utils.embed_builder(title="Test Embed", description="").title, self.embed.title,
                         "Titles not matching")

    def test_embed_builder_description(self):
        self.assertEqual(self.embed_utils.embed_builder(title="Test Embed", description="Test Description").description,
                         self.embed.description, "Descriptions not matching")

    def test_embed_builder_colour(self):
        self.assertEqual(self.embed_utils.embed_builder(title="Test Embed", description="Test Description").color,
                         self.embed.color, "Colours not matching")

    def test_embed_builder_footer(self):
        self.embed.set_footer(text=config.BOT_NAME)

        self.assertEqual(self.embed_utils.embed_builder(title="Test Embed", description="Test Description",
                                                        has_footer=True, footer=config.BOT_NAME).footer.text,
                         self.embed.footer.text, "Footer Text not matching")

    def test_embed_builder_no_footer(self):
        self.embed.set_footer(text=config.BOT_NAME)

        self.assertNotEqual(self.embed_utils.embed_builder(title="Test Embed", description="Test Description",
                                                           has_footer=False).
                            footer.text, self.embed.footer.text, "The Footer text should be empty!")

    def test_embed_builder_time_stamp(self):
        self.assertIsNotNone(self.embed_utils.embed_builder(title="Test Embed", description="Test Description",
                                                            time_stamp=True).timestamp)
