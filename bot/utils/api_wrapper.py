import aiohttp
import socket

from googleapiclient import errors
from googleapiclient.discovery import build
from oauth2client import file as oauth_file, client, tools
from bot.config import token, config


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


class GoogleAPIWrapper:

    def __init__(self, bot):
        socket.setdefaulttimeout(600)
        self.bot = bot
        self.scopes = config.GOOGLE_CLOUD_PLATFORM_OAUTH_SCOPES
        self.oauth2_store = oauth_file.Storage(config.GOOGLE_CLOUD_PLATFORM_CLIENT_OAUTH_CREDENTIALS_FILE)

    async def run_apps_script(self, script_id, function, parameters):
        return await self.bot.loop.run_in_executor(None, self.execute_apps_script, script_id, function, parameters)

    def execute_apps_script(self, script_id, function, parameters):
        creds = self.oauth2_store.get()

        if not creds or creds.invalid:
            flow = client.flow_from_clientsecrets(config.GOOGLE_CLOUD_PLATFORM_CLIENT_SECRETS_FILE, self.scopes)
            creds = tools.run_flow(flow, self.oauth2_store)

        service = build('script', 'v1', credentials=creds, cache_discovery=False)
        request = {"function": function, "parameters": parameters, "devMode": True}

        try:
            response = service.scripts().run(body=request, scriptId=script_id).execute()
            return response

        except errors.HttpError as e:
            print(f"[GOOGLE] Error while executing Apps Script {script_id}: {e.content}")
            return None
