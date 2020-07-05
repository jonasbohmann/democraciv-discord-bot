import aiohttp

from dciv_bot.config import token, config


class RedditAPIWrapper:

    def __init__(self, bot):
        self.bot = bot
        self.bearer_token = None

    async def refresh_reddit_bearer_token(self):
        """Gets a new access_token for the Reddit API with a refresh token that was previously acquired by following
         this guide: https://github.com/reddit-archive/reddit/wiki/OAuth2"""

        auth = aiohttp.BasicAuth(login=token.REDDIT_CLIENT_ID, password=token.REDDIT_CLIENT_SECRET)
        post_data = {"grant_type": "refresh_token", "refresh_token": token.REDDIT_REFRESH_TOKEN}
        headers = {"User-Agent": f"democraciv-discord-bot {config.BOT_VERSION} by DerJonas - u/Jovanos"}

        async with self.bot.session.post("https://www.reddit.com/api/v1/access_token",
                                         data=post_data, auth=auth, headers=headers) as response:
            if response.status == 200:
                r = await response.json()
                self.bearer_token = r['access_token']

    async def post_to_reddit(self, data: dict) -> bool:
        """Submit post to specified subreddit"""

        await self.refresh_reddit_bearer_token()

        headers = {"Authorization": f"bearer {self.bearer_token}",
                   "User-Agent": f"democraciv-discord-bot {config.BOT_VERSION} by DerJonas - u/Jovanos"}

        try:
            async with self.bot.session.post("https://oauth.reddit.com/api/submit", data=data,
                                             headers=headers) as response:
                if response.status != 200:
                    print(f"[BOT] ERROR - Error while posting to Reddit, got status {response.status}.")
                    return False
                return True
        except Exception as e:
            print(f"[BOT] ERROR - Error while posting to Reddit: {e}")
            return False
