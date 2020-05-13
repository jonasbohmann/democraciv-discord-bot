##  democraciv-discord-bot
 [![Discord](https://discordapp.com/api/guilds/208984105310879744/embed.png)](http://discord.gg/j7sZ3tD) ![Python Version](https://img.shields.io/badge/python-3.7%20%7C%203.8-blue) [![Build Status](https://travis-ci.com/jonasbohmann/democraciv-discord-bot.svg?branch=master)](https://travis-ci.com/jonasbohmann/democraciv-discord-bot)

General-purpose Discord Bot with unique features designed for the r/Democraciv Discord. 

Provides useful information, political party & role management and much more. 

##  Requirements

*  [Python](https://www.python.org/downloads//) 3.7 or newer
*  [discord.py](https://github.com/Rapptz/discord.py) 1.3.0 or newer
*  [PostgreSQL](https://www.postgresql.org/) 9.6 or newer 

**Run `pip install -r requirements.txt` to install all required dependencies.**

##  Features
*  Announcements to both our Discord and our subreddit for:
    - live streams on twitch.tv/democraciv
    - live streams on the Democraciv YouTube channel
    - new video uploads from the Democraciv YouTube channel
    - new posts on reddit.com/r/democraciv *(only to Discord obviously)*
*  Helps the Speaker of the Legislature with legislative sessions and submissions (bills & motions)
*  Supports the Executive with vetoes by keeping them up-to-date with passed bills from the Legislature
*  Keeps track of all legislative sessions, bills, motions, ministry vetoes and laws
*  Generates the voting form as a Google Form for legislative sessions
*  Users can search for active laws by their name or by automatically generated tags
*  Join and leave political parties and see their members and ranking
*  Tags: Users can save text and images for later retrieval to command-like tags
*  Starboard: A starboard on Discord _and_ weekly posts to r/Democraciv with last week's starboard as a sort of "summary" of newsworthy Discord messages to our subreddit
*  Built-in STV calculator
*  Smart Wikipedia and Sid Meier's Civilization Wikia queries
*  Welcome messages & default roles
*  Selfroles (self-assignable roles) 
*  Detailed help command with examples of command usage
*  Gets the current time in over 400 timezones
*  Moderation commands 
*  Alt detection
*  Event logging 


##  Installation

*As some features are implemented in a way to fit the very specific needs and use cases of the Democraciv Discord, it is not recommended 
to run the bot yourself as you might run into unexpected errors. Instead, invite the bot to your server with this 
 [link](https://discordapp.com/oauth2/authorize?client_id=486971089222631455&scope=bot&permissions=2081418487).*

After installing all the dependencies, create a `token.py` in the config folder.

The file should look like this:

```
# Token
TOKEN = ""
TIMEZONEDB_API_KEY = ""
YOUTUBE_DATA_V3_API_KEY = ""

# Reddit
REDDIT_USERNAME = ""
REDDIT_CLIENT_ID = ""
REDDIT_CLIENT_SECRET = ""
REDDIT_REFRESH_TOKEN = ""

# Twitch Config
TWITCH_CLIENT_ID = ""
TWITCH_CLIENT_SECRET = ""
TWITCH_OAUTH_APP_ACCESS_TOKEN = ""

# PostgreSQL config
POSTGRESQL_USER = ""
POSTGRESQL_PASSWORD = ""
POSTGRESQL_HOST = ""
POSTGRESQL_DATABASE = ""
```

Add the token of your Discord App, your Twitch Helix API authorization if you enabled the Twitch module, your API key for the 
YouTube Data v3 API if you enabled YouTube notifications, your TimeZoneDB API Key, and your PostgreSQL configuration like above. 

Once `token.py` is set up, take a look at `config.py` in the same folder and adjust everything to your needs.

After you've done all that, run `bot.py`.

####  Database

This bot needs a PostgreSQL database to run. To install and configure PostgreSQL, head [here](https://www.postgresql.org/).
 The bot was tested with PostgreSQL 9.6, 11.5 and 12.1, everything in between should work.


You only need to create an empty database, the bot will then fill that with tables on startup.


####  Twitch 

If you want to use the Twitch announcements feature, you have to create an app [here](https://dev.twitch.tv/console/apps). 
Then, copy its Client ID and the Client Secret and add it to the `token.py` in the config folder. It's strongly recommended to also
[obtain an OAuth app access token](https://dev.twitch.tv/docs/authentication/getting-tokens-oauth#oauth-client-credentials-flow)
 and add it to `token.py` too. While the bot will obtain the app access token itself (if not provided) via the
Client ID and Client Secret, the token will not persist bot restarts, resulting in useless API requests to the Twitch API for 
a new token. 

App Access Tokens expire after around 58 days. If that happens, the bot will obtain a new one and notify you to replace that new token
in `token.py`.

You can configure everything else that is Twitch related in `config.py`.


####  Reddit 

Notifications for new posts from a subreddit are enabled by default, but can be disabled in the `config.py`. Unlike the
Twitch Notification module, we don't need to register an API key for Reddit.

If you want to make the bot post the weekly Starboard to a subreddit, you do have to provide the client ID, client secret and 
a **refresh token** (not application token!) of your reddit app. Follow this [guide](https://github.com/reddit-archive/reddit/wiki/OAuth2) on how to get these. 
Make sure your refresh token has the `submit` scope. 

You can configure everything else that is Reddit related in `config.py`.


####  YouTube 

Notifications for new video uploads and livestreams from a YouTube channel are enabled by default, but can be disabled in the `config.py`. You'll need
an API key for the YouTube Data v3 API from Google. [This](https://developers.google.com/youtube/v3) has more information on how to get one.

You can configure everything else that is YouTube related in `config.py`.


#### Google Cloud Platform

The Bot uses the Google Apps Script API to remotely execute the Apps Script that generates the voting form as a Google Form for
legislative sessions. You need to create a Google Cloud Platform project and then create OAuth credentials for that project. Download the credentials as JSON from your Google Cloud Platform Console
and put that file to the filepath that is specified as `GOOGLE_CLOUD_PLATFORM_CLIENT_SECRETS_FILE` in `config.py`. The file in `GOOGLE_CLOUD_PLATFORM_CLIENT_OAUTH_CREDENTIALS_FILE` 
will be created by the bot itself. The first time this is run, **it will open your web browser** to create OAuth Access Tokens based on your Google Account.
 
The Apps Script must be in the same Google Cloud Platform project as the OAuth credentials for the caller. 

This setup is a bit more complex than the other APIs. Follow these guides: 

*   [Google Cloud Platform](https://console.cloud.google.com/)
*   [Google Apps Script API](https://developers.google.com/apps-script/api/concepts)
*   [Python Quickstart](https://developers.google.com/apps-script/api/quickstart/python)
*   [REST Reference](https://developers.google.com/apps-script/api/reference/rest)

##  Modules
You can add and remove modules by adding or removing them from `initial_extensions` in `bot.py`.

Module | Description 
------------ | ------------- |
module.admin | Debug commands for the developer |
module.misc | Miscellaneous commands | 
module.meta | Commands regarding the bot itself |
module.tags | Tags: Users can save text for later retrieval to command-like tags | 
module.guild | Configure various functions of this bot for your guild |
module.roles | Add or remove roles from you |
module.starboard | A Starboard for the Democraciv guild. If a message receives at least 4 ⭐ reactions, it will be added to the Starboard. |
module.time | Get the current time in a number of different timezones |
module.wiki | Search for a topic on Wikipedia and the Sid Meier's Civilization Fandom wiki |
module.democraciv.legislature | Helps the Speaker of the Legislature with keeping track of submitted bills, motions and legislative sessions in general |
module.democraciv.ministry | Helps the Prime Minister with keeping track of passed bills that need to be voted on (vetoed) |
module.democraciv.supremecourt | Collection of links for Supreme Court Justices |
module.democraciv.laws | Lists all laws passed by the Legislature & Ministry and allows to search for laws by automatically generated tags |
module.democraciv.elections | Calculate results for STV elections |
module.democraciv.parties | Join and leave political parties |
module.democraciv.moderation | Tools for the Moderation Team of Democraciv |
event.logging | Logs events (member joins/leaves, message deleted/edited etc.) to a specified channel |
event.error_handler | Handles internal errors |
event.reddit | Handles notifications when there's a new post on r/democraciv |
event.twitch | Handles notifications when twitch.tv/democraciv is live |
event.youtube | Handles notifications when a new video or livestream on the Democraciv YouTube channel was uploaded or started|


##  Roadmap

####  Update 0.13.0 - The Performance & Stability Update ✅

*  ~~Refactor client.py~~
*  ~~Rewrite event modules~~
*  ~~Introduce custom exceptions~~
*  ~~Introduce utils to save time & code~~
*  ~~Replace blocking libraries (praw, wikipedia) with aiohttp API calls~~

####  Update 0.14.0 - The SQL Update ✅

*  ~~Add a PostgreSQL database~~
*  ~~Migrate `guilds.json`, `parties.json` and `last_reddit_post.json` to new database~~
*  ~~Make roles case-insensitive~~
*  ~~Rewrite -addparty, -addrole, -deleteparty, -deleterole, -addalias, -deletealias to be safer and cover all needed values
for database~~
*  ~~Refactor asyncio.wait_for() tasks in guild.py~~
*  ~~Refactor help.py~~ (Update 0.14.2)


####  Update 0.15.0 - The Government Update ✅

*  ~~Add STV calculation~~
*  ~~Add Legislature dashboard~~
*  ~~Add Ministry dashboard~~
*  ~~Introduce system to keep track of legislative sessions, ministry vetoes and active laws~~
*  ~~Rewrite the `time.py` module~~


####  Update 0.16.0 - The Moderation Update ✅

*  ~~Add a Moderation module with `-kick`, `-ban` etc. commands~~
*  ~~Add anonymous report feature~~
*  ~~Add multiple event notifications for #moderation-notifications~~
*  ~~Add alt detection~~

####  Update 0.17.0 - The Suggestions Update ✅

*  ~~Starboard-like system for the #press channel with weekly summaries to Reddit~~
*  ~~Add motion support to -legislature withdraw~~
*  ~~Add utility mod commands to support the process between MKs~~
*  ~~Allow Speaker and Ministry to pass multiple bills in a single command~~
*  ~~Add -mergeparties command~~
*  ~~Wait a certain amount of time for multiple consecutive -legislature pass to bundle messages in #gov-announcements~~
*  ~~Refactor & cleanup for 1.0 release~~



##  Democraciv Discord Server
Join the [Democraciv Discord Server](https://discord.gg/AK7dYMG) to see the bot in action.

---

Contact @DerJonas#8036 on Discord if you have any questions left.