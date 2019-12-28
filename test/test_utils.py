import discord
import unittest

from config import config
from util.utils import EmbedUtils


class TestEmbedUtils(unittest.TestCase):

    def setUp(self):
        self.embed_utils = EmbedUtils()
        self.embed = discord.Embed(title="Test Embed", description="Test Description", colour=0x7f0000)

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
                                                        has_footer=True).footer.text,
                         self.embed.footer.text, "Footer Text not matching")

    def test_embed_builder_footer_icon(self):
        self.embed.set_footer(icon_url=config.BOT_ICON_URL)

        self.assertEqual(self.embed_utils.embed_builder(title="Test Embed", description="Test Description",
                                                        has_footer=True).
                         footer.icon_url, self.embed.footer.icon_url, "Footer Icon URL not matching")

    def test_embed_builder_no_footer(self):
        self.embed.set_footer(text=config.BOT_NAME)

        self.assertNotEqual(self.embed_utils.embed_builder(title="Test Embed", description="Test Description",
                                                           has_footer=False).
                            footer.text, self.embed.footer.text, "The Footer text should be empty!")

    def test_embed_builder_time_stamp(self):
        self.assertIsNotNone(self.embed_utils.embed_builder(title="Test Embed", description="Test Description",
                                                            time_stamp=True).timestamp)
