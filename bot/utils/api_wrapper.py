import logging
import os
import pickle
import aiohttp
import socket

from googleapiclient import errors
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport import requests

from bot.config import token, config, exceptions


class RedditAPIWrapper:
    def __init__(self, bot):
        self.bot = bot
        self.bearer_token = None

    async def refresh_reddit_bearer_token(self):
        """Gets a new access_token for the Reddit API with a refresh token that was previously acquired by following
        this guide: https://github.com/reddit-archive/reddit/wiki/OAuth2"""

        auth = aiohttp.BasicAuth(login=token.REDDIT_CLIENT_ID, password=token.REDDIT_CLIENT_SECRET)
        post_data = {
            "grant_type": "refresh_token",
            "refresh_token": token.REDDIT_REFRESH_TOKEN,
        }
        headers = {"User-Agent": f"democraciv-discord-bot {config.BOT_VERSION} by DerJonas - u/Jovanos"}

        async with self.bot.session.post(
                "https://www.reddit.com/api/v1/access_token",
                data=post_data,
                auth=auth,
                headers=headers,
        ) as response:
            if response.status == 200:
                r = await response.json()
                self.bearer_token = r["access_token"]

    async def post_to_reddit(self, data: dict) -> bool:
        """Submit post to specified subreddit"""

        await self.refresh_reddit_bearer_token()

        headers = {
            "Authorization": f"bearer {self.bearer_token}",
            "User-Agent": f"democraciv-discord-bot {config.BOT_VERSION} by DerJonas - u/Jovanos",
        }

        try:
            async with self.bot.session.post(
                    "https://oauth.reddit.com/api/submit", data=data, headers=headers
            ) as response:
                if response.status != 200:
                    logging.error(f"Error while posting to Reddit, got status {response.status}.")
                    return False
                return True
        except Exception as e:
            logging.error(f"Error while posting to Reddit: {e}")
            return False


class GoogleAPIError(exceptions.DemocracivBotException):
    message = f"{config.NO} Something went wrong during the execution of a Google Apps Script. " \
              f"Please try again later or contact the developer. Make sure that, if you have given me the URL " \
              f"of a Google Docs or Google Forms, that I have edit permissions on this document if needed."


class GoogleAPIWrapper:
    def __init__(self, bot):
        socket.setdefaulttimeout(600)
        self.bot = bot
        self.scopes = config.GOOGLE_CLOUD_PLATFORM_OAUTH_SCOPES

    async def run_apps_script(self, script_id, function, parameters):
        try:
            result = await self.bot.loop.run_in_executor(None, self._execute_apps_script, script_id, function, parameters)

            if "error" in result:
                raise GoogleAPIError()

            return result
        except Exception:
            raise GoogleAPIError()

    def _execute_apps_script(self, script_id, function, parameters):
        google_credentials = None

        if os.path.exists('config/google_oauth_token.pickle'):
            with open('config/google_oauth_token.pickle', 'rb') as google_token:
                google_credentials = pickle.load(google_token)

        if not google_credentials or not google_credentials.valid:
            if google_credentials and google_credentials.expired and google_credentials.refresh_token:
                google_credentials.refresh(requests.Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    config.GOOGLE_CLOUD_PLATFORM_CLIENT_SECRETS_FILE,
                    self.scopes)
                google_credentials = flow.run_local_server(port=0)

            with open('config/google_oauth_token.pickle', 'wb') as google_token:
                pickle.dump(google_credentials, google_token)

        service = build("script", "v1", credentials=google_credentials, cache_discovery=False)
        request = {"function": function, "parameters": parameters, "devMode": True}

        try:
            return service.scripts().run(body=request, scriptId=script_id).execute()
        except errors.HttpError as e:
            logging.error(f"Error while executing Apps Script {script_id}: {e.content}")
            raise e
