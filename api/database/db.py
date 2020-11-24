import asyncio
import logging
import asyncpg

DB_SCHEMA = """CREATE TABLE IF NOT EXISTS reddit_webhooks(
                    id serial primary key,
                    subreddit text,
                    webhook_id bigint UNIQUE,
                    webhook_url text UNIQUE,
                    guild_id bigint,
                    channel_id bigint    
                );
                
                CREATE TABLE IF NOT EXISTS twitch_webhooks(
                    id serial primary key,
                    streamer text,
                    webhook_id bigint UNIQUE,
                    webhook_url text UNIQUE,
                    guild_id bigint,
                    channel_id bigint,
                    everyone_ping bool DEFAULT FALSE
                );

                CREATE TABLE IF NOT EXISTS reddit_posts(
                    id text UNIQUE
                );

                CREATE TABLE IF NOT EXISTS youtube_uploads(
                    id text UNIQUE
                );

                CREATE TABLE IF NOT EXISTS youtube_streams(
                    id text UNIQUE
                );

                CREATE TABLE IF NOT EXISTS twitch_streams(
                    id text UNIQUE
                );
            """


class Database:
    def __init__(self, *, dsn: str):
        self._loop = asyncio.get_event_loop()
        self._loop.create_task(self.setup(dsn))

    async def setup(self, dsn: str):
        self._pool: asyncpg.pool.Pool = await asyncpg.create_pool(dsn=dsn, loop=self._loop)
        await self.apply_schema()
        logging.info("successfully connected to database")

    async def apply_schema(self):
        await self._pool.execute(DB_SCHEMA)

    async def add_reddit_scraper(self, scraper):
        await self._pool.execute(
            "INSERT INTO reddit_webhooks "
            "(subreddit, webhook_id, webhook_url, guild_id, channel_id) "
            "VALUES ($1, $2, $3, $4, $5)",
            scraper.subreddit,
            scraper.webhook_id,
            scraper.webhook_url,
            scraper.guild_id,
            scraper.channel_id,
        )

    async def remove_reddit_scraper(self, webhook_id: int, guild_id: int):
        # guild_id is used to "authenticate" removal request
        record = await self._pool.fetchrow(
            "DELETE FROM reddit_webhooks WHERE id = $1 AND guild_id = $2 RETURNING subreddit, webhook_url, channel_id",
            webhook_id,
            guild_id,
        )

        if not record:
            return None, None, None

        return record["subreddit"], record["webhook_url"], record["channel_id"]

    async def get_reddit_webhooks_by_guild(self, guild_id: int):
        return await self._pool.fetch(
            "SELECT id, subreddit, webhook_id, webhook_url FROM reddit_webhooks WHERE guild_id = $1", guild_id
        )

    async def is_reddit_post_new(self, post_id: int):
        """Returns True if the Reddit post is new"""

        status = await self._pool.execute("INSERT INTO reddit_posts (id) VALUES ($1) ON CONFLICT DO NOTHING", post_id)
        return False if status == "INSERT 0 0" else True
