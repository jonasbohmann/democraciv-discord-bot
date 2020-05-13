import socket

from config import config

from googleapiclient import errors
from googleapiclient.discovery import build
from oauth2client import file as oauth_file, client, tools


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
