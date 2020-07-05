import asyncio
import enum
import re
import asyncpg
from dciv_bot.config import token

"""Migrate database from 1.* to 1.2 as users can now decide whether tags should be embedded by themselves."""


class TagContentType(enum.Enum):
    TEXT = 1
    IMAGE = 2
    INVITE = 3
    CUSTOM_EMOJI = 4
    YOUTUBE_TENOR_GIPHY = 5
    VIDEO = 6
    PARTIAL_IMAGE = 7


async def get_db():
    return await asyncpg.create_pool(user=token.POSTGRESQL_USER,
                                     password=token.POSTGRESQL_PASSWORD,
                                     database=token.POSTGRESQL_DATABASE,
                                     host=token.POSTGRESQL_HOST)


def get_tag_content_type(tag_content: str) -> TagContentType:
    emoji_pattern = re.compile(r"<(?P<animated>a)?:(?P<name>[0-9a-zA-Z_]{2,32}):(?P<id>[0-9]{15,21})>")
    discord_invite_pattern = re.compile(r"(?:https?://)?discord(?:app\.com/invite|\.gg)/?[a-zA-Z0-9]+/?")
    url_pattern = re.compile(
        r"((http|https)\:\/\/)?[a-zA-Z0-9\.\/\?\:@\-_=#]+\.([a-zA-Z]){2,6}([a-zA-Z0-9\.\&\/\?\:@\-_=#])*")

    url_endings_image = ('.jpeg', '.jpg', '.png', '.gif', '.webp', '.bmp', '.img', '.svg')
    url_endings_video = ('.avi', '.mp4', '.mp3', '.mov', '.flv', '.wmv')

    if url_pattern.fullmatch(tag_content) and (tag_content.lower().endswith(url_endings_image)):
        return TagContentType.IMAGE

    elif url_pattern.match(tag_content) and (tag_content.lower().endswith(url_endings_image)):
        return TagContentType.PARTIAL_IMAGE

    elif url_pattern.match(tag_content) and (tag_content.lower().endswith(url_endings_video)):
        return TagContentType.VIDEO

    elif url_pattern.match(tag_content) and any(
            s in tag_content for s in ['youtube', 'youtu.be', 'tenor.com', 'gph.is', 'giphy.com']):
        return TagContentType.YOUTUBE_TENOR_GIPHY

    elif emoji_pattern.fullmatch(tag_content):
        return TagContentType.CUSTOM_EMOJI

    elif discord_invite_pattern.match(tag_content):
        return TagContentType.INVITE

    return TagContentType.TEXT


async def main():
    db = await get_db()

    async with db.acquire() as connection:
        async with connection.transaction():
            tags = await connection.fetch("SELECT * FROM guild_tags")

            for record in tags:
                ct = get_tag_content_type(record['content'])

                if ct is TagContentType.IMAGE or ct is TagContentType.TEXT:
                    print(f"Set {record['name']} with CT {ct} to be embedded.")
                    await connection.execute("UPDATE guild_tags SET is_embedded = true WHERE id = $1", record['id'])

                else:
                    print(f"Set {record['name']} with CT {ct} to be text.")
                    await connection.execute("UPDATE guild_tags SET is_embedded = false WHERE id = $1", record['id'])


if __name__ == '__main__':
    asyncio.run(main())
    print("Migration complete.")
