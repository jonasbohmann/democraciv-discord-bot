import discord
from aiohttp import web


class BankListener:

    def __init__(self, bot):
        self.bot = bot
        self.app = web.Application()
        self.app.add_routes([web.post('/dm', self.send_dm)])
        self.runner = web.AppRunner(self.app)
        self.bot.loop.create_task(self.setup())

    async def setup(self):
        await self.runner.setup()
        site = web.TCPSite(self.runner, 'localhost', 8080)
        await site.start()

    async def send_dm(self, request):
        json = await request.json()

        for target in json['targets']:
            user = self.bot.get_user(target)

            if user is None:
                continue

            msg = json['message'] if json['message'] else None
            embed = discord.Embed.from_dict(json['embed']) if json['embed'] else None

            try:
                await user.send(content=msg, embed=embed)
            except discord.Forbidden:
                continue
        
        return web.json_response({'ok': 'ok'})

