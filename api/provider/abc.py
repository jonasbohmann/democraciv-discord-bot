import abc
import asyncio
import logging
import typing
import aiohttp


class ProviderManager(abc.ABC):
    provider: str
    target: str
    table: str

    def __init__(self, *, db):
        self.db = db
        self._loop = asyncio.get_event_loop()
        self._loop.create_task(self._make_aiohttp_session())
        self._lock = asyncio.Lock()
        self._webhooks: typing.Dict[str, typing.Any] = {}
        self._loop.create_task(self._bulk_start_all())

    async def _make_aiohttp_session(self):
        self._session = aiohttp.ClientSession()

    async def _bulk_start_all(self):
        if not self.db.ready:
            await asyncio.sleep(5)

        webhooks = await self.db.pool.fetch(f"SELECT {self.target}, webhook_url FROM {self.table}")

        for webhook in webhooks:
            self._loop.create_task(self._start_webhook(target=webhook[self.target],
                                                       webhook_url=webhook['webhook_url']))

        logging.info(f"started {len(webhooks)} {self.provider} hooks")

    async def add_webhook(self, config):
        await self.db.pool.execute(f"INSERT INTO {self.table} ({self.target}, webhook_id, webhook_url, "
                                   "guild_id, channel_id)"
                                   "VALUES ($1, $2, $3, $4, $5)",
                                   config.target, config.webhook_id, config.webhook_url,
                                   config.guild_id, config.channel_id)
        return await self._start_webhook(target=config.target, webhook_url=config.webhook_url)

    async def new_webhook_for_target(self, *, target: str, webhook_url: str):
        pass

    async def no_more_webhooks_for_target(self, *, target: str, webhook_url: str):
        pass

    async def _start_webhook(self, *, target: str, webhook_url: str):
        async with self._lock:
            if target in self._webhooks:
                self._webhooks[target].add(webhook_url)
                return self._webhooks[target]
            else:
                result = await self.new_webhook_for_target(target=target, webhook_url=webhook_url)
                self._webhooks[target] = {webhook_url}
                return result

    async def _remove_webhook(self, *, target: str, webhook_url: str):
        if target not in self._webhooks:
            return

        async with self._lock:
            if len(self._webhooks[target]) == 1 and webhook_url in self._webhooks[target]:
                await self.no_more_webhooks_for_target(target=target, webhook_url=webhook_url)
                del self._webhooks[target]
            else:
                self._webhooks[target].remove(webhook_url)

    async def remove_webhook(self, *, hook_id: int, guild_id: int):
        record = await self.db.pool.fetchrow(f"DELETE FROM {self.table} WHERE id = $1 AND guild_id = $2 "
                                             f"RETURNING {self.target}, webhook_url, channel_id", hook_id, guild_id)

        if not record:
            return {"error": "not found"}

        safe_to_delete = await self._can_discord_webhook_be_deleted(record['channel_id'])
        js = dict(record)
        js['safe_to_delete'] = safe_to_delete

        self._loop.create_task(self._remove_webhook(target=record[self.target], webhook_url=record['webhook_url']))
        return js

    async def _can_discord_webhook_be_deleted(self, channel_id: int):
        others_exist = await self.db.pool.fetch("SELECT true AS other_exists FROM reddit_webhook FULL "
                                                "OUTER JOIN twitch_webhook ON "
                                                "reddit_webhook.channel_id = twitch_webhook.channel_id "
                                                "WHERE reddit_webhook.channel_id = $1 OR "
                                                "twitch_webhook.channel_id = $1", channel_id)
        if others_exist:
            return False
        else:
            return True

    async def get_webhooks_per_guild(self, guild_id: int):
        records = await self.db.pool.fetch(f"SELECT * FROM {self.table} WHERE guild_id = $1", guild_id)
        return [dict(record) for record in records]

    async def clear_per_guild(self, guild_id: int):
        hooks = await self.get_webhooks_per_guild(guild_id=guild_id)
        result = []

        for hook in hooks:
            js = await self.remove_webhook(hook_id=hook['id'], guild_id=guild_id)
            result.append(js)

        return result
