## democraciv-discord-bot
Discord Bot for r/Democraciv written in Python 3. Provides useful information, political party management and more. 

## Requirements
**Important**: This bot does not work with the latest discord.py from [pypi](https://pypi.org/project/discord.py/)! You have to install 
an older version from git, see `requirements.txt` for details.
Updating to discord.py 1.1.0 is planned.


* [Python](https://www.python.org/downloads//) 3.6 or higher
* [discord.py-rewrite](https://github.com/Rapptz/discord.py/tree/3f06f247c039a23948e7bb0014ea31db533b4ba2) commit 3f06f24
* [wikipedia](https://pypi.org/project/wikipedia/) 1.4.0 or higher
* [praw](https://github.com/praw-dev/praw) 6.2.0 or higher
 
Check `requirements.txt` for details - or just use `pip install -r requirements.txt`.

## Installation
After installing all the dependencies, create a `token.json` in the config folder.

The file should look like this:
```
 {
  "token": "INSERT_TOKEN_HERE"
  "twitchAPIKey": "INSERT_TWITCH_API_KEY_HERE",
  "redditClientID": "INSERT_REDDIT_CLIENT_ID_HERE",
  "redditClientSecret": "INSERT_REDDIT_CLIENT_SECRET_HERE"
 }
```
Add the token of your Discord App like above. Then, run `client.py`.

### Twitch 

If you want to use the Twitch announcements feature, you have to get an API key from [here](https://dev.twitch.tv/console/apps)
and add it to the `token.json` in the config folder.

You can configure everything else that is Twitch related in the `config.json`.

**If you do not want to use the Twitch announcements feature**, you have to set `enableTwitchAnnouncements` in the
`config.json` to `false`.

### Reddit 

If you want to use the Reddit announcements feature, you first have to create a new Reddit app [here](https://www.reddit.com/prefs/apps). 
Set your app to be used as a personal script, then copy the new client ID and client secret into your `token.json`.

You can configure everything else that is Reddit related in the `config.json`.

**If you do not want to use the Reddit announcements feature**, you have to set `enableRedditAnnouncements` in the
`config.json` to `false`.


## Features
* Modular system for commands
* Help command that automatically scales
* Announcements for twitch.tv/democraciv
* Announcements for new post from reddit.com/r/democraciv
* Political party (role) management
* Event Logging 

## Modules
You can add and remove modules by adding or removing them from `initial_extensions` in `client.py`.

Module | Description | Requires no permissions
------------ | ------------- | -------------
module.links | Collection of useful links for the game (Wiki, Constitution, political parties etc.) | ✅
module.about | Commands regarding the bot itself | ✅
module.admin | Re-, un- and load modules and the config | ❌
module.fun | Just -say for now | ❌
module.help | Scaling -help command | ✅
module.random | Common choice commands (Heads or Tails etc.) | ✅
module.parties | Join and leave political parties | ✅
module.time | Get current time in different timezones | ✅
module.vote | Start voting on a specified topic with emojis *(Under construction)* | ✅
module.wikipedia | Search for a topic on wikipedia | ✅
event.logging | Logs events (member joins/leaves etc.) to a specified channel | 
event.error_handler | Handles internal erros | 

## Planned
* Proportional Representation voting
* SQL Database for seperate configs per server

## Democraciv Discord Server
Join the [Democraciv Discord Server](https://discord.gg/AK7dYMG) to see the bot in action.

---

Contact @DerJonas#8109 on Discord if you have any questions left.
