import asyncio
import logging
import asyncpg


class Database:
    def __init__(self, *, dsn: str):
        self._loop = asyncio.get_event_loop()
        self._pool: asyncpg.pool.Pool = None
        self._loop.create_task(self.setup(dsn))

    async def setup(self, dsn: str):
        self._pool = await asyncpg.create_pool(dsn=dsn, loop=self._loop)
        await self.apply_schema()
        logging.info("successfully connected to database")

    async def apply_schema(self):
        DB_SCHEMA = """
                CREATE TABLE IF NOT EXISTS reddit_scraper(
                    id serial primary key,
                    subreddit text UNIQUE
                );
                
                CREATE TABLE IF NOT EXISTS reddit_discord_webhooks(
                    scraper serial references reddit_scraper(id),
                    webhook_url text UNIQUE 
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

        await self._pool.execute(DB_SCHEMA)

    async def is_reddit_post_new(self, post_id: int):
        """Returns True if the Reddit post is new"""

        status = await self._pool.execute("INSERT INTO reddit_posts (id) VALUES ($1) ON CONFLICT DO NOTHING", post_id)
        return False if status == "INSERT 0 0" else True
