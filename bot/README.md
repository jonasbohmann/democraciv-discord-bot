##  bot

General-purpose Discord Bot with lots of unique features designed for the r/Democraciv Discord. 


##  Requirements

*  [Python](https://www.python.org/downloads/) 3.7 or newer
*  [discord.py](https://github.com/Rapptz/discord.py) 1.6.0 or newer
*  [PostgreSQL](https://www.postgresql.org/) 9.6 or newer 

Run `pip install -r requirements.txt` to install all required dependencies.

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
*  Generates an up-to-date Legal Code based on the active laws as a Google Docs document
*  Users can search for active laws by their name or by automatically generated tags
*  Join and leave political parties 
*  Tags: Users can save text and images for later retrieval to command-like tags
*  Starboard: A starboard on Discord _and_ weekly posts to r/Democraciv with last week's starboard as a sort of "summary" of newsworthy Discord messages to our subreddit
*  Wikipedia queries
*  Welcome messages & role on join
*  Selfroles (self-assignable roles) 
*  Detailed help command with examples of command usage
*  Gets the current time in over 400 timezones
*  Moderation commands 
*  Event logging 


##  Installation

*As some features are implemented in a way to fit the very specific needs and use cases of the Democraciv Discord, care must be taken if you want
to run the bot yourself as you might run into unexpected errors or behaviour.*

After installing all the dependencies, create a `token.py` in the config folder.

The file should look like this:

```
# Token
TOKEN = ""

# PostgreSQL config
POSTGRESQL_USER = ""
POSTGRESQL_PASSWORD = ""
POSTGRESQL_HOST = ""
POSTGRESQL_DATABASE = ""
```

Add the token of your Discord App and your PostgreSQL configuration like above. 

Once `token.py` is set up, take a look at `config_example.py` and `mk_example.py` in the same folder and adjust everything to your needs.

Remember to rename both `config_example.py` and `mk_example.py` to `config.py` and `mk.py` before you run the bot.

#### Docker

You can use the supplied Dockerfile to run the bot as a Docker container.

The `docker-compose.yml` in the project root will start a bot container, an API container, and a PostgreSQL container.

#### Database

This bot needs a PostgreSQL database to run. To install and configure PostgreSQL, head [here](https://www.postgresql.org/).
 The bot was tested with every major PostgreSQL version, 9.6, 11.5, 12.1 and 13.1. Every version should work.


You only need to create an empty database, the bot will then fill that with tables on startup.


#### Google Cloud Platform

The Bot uses the Google Apps Script API to remotely execute Google Apps Scripts.

You need to create a Google Cloud Platform project and then create OAuth credentials for that project. Download the credentials as JSON from your Google Cloud Platform Console
and put that file to the filepath that is specified as `GOOGLE_CLOUD_PLATFORM_CLIENT_SECRETS_FILE` in `config.py`. The first time this is run, **it will open your web browser** to create OAuth Access Tokens based on your Google Account.
 
The Apps Script must be in the same Google Cloud Platform project as the OAuth credentials for the caller. 

This setup is a bit more complex than the other APIs. Follow these guides: 

*   [Google Cloud Platform](https://console.cloud.google.com/)
*   [Google Apps Script API](https://developers.google.com/apps-script/api/concepts)
*   [Python Quickstart](https://developers.google.com/apps-script/api/quickstart/python)
*   [REST Reference](https://developers.google.com/apps-script/api/reference/rest)


