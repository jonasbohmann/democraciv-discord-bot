## democraciv-discord-bot
Discord Bot for r/Democraciv written in Python 3. Provides useful information, political party management and more. 

## Requirements

* [Python](https://www.python.org/downloads//) 3.6 or higher
* [discord.py](https://github.com/Rapptz/discord.py) 1.0.0 or higher

**Run `pip install -r requirements.txt` to install all required dependencies.**

## Installation
After installing all the dependencies, create a `token.json` in the config folder.

The file should look like this:
```
 {
  "token": "INSERT_TOKEN_HERE"
  "twitchAPIKey": "INSERT_TWITCH_API_KEY_HERE"
 }
```
Add the token of your Discord App like above. Then, run `client.py`.

#### Twitch 

If you want to use the Twitch announcements feature, you have to get an API key from [here](https://dev.twitch.tv/console/apps)
and add it to the `token.json` in the config folder.

You can configure everything else that is Twitch related in the `config.json`.

If you do not want to use the Twitch announcements feature, you have to set `enableTwitchAnnouncements` in the
`config.json` to `false`.

#### Reddit 

Notifications for new posts from a subreddit are enabled by default, but can be disabled in the `config.json`. Unlike the
Twitch Notification module, we don't need to register an API key for Reddit.

You can configure everything else that is Reddit related in the `config.json`.

If you do not want to use the Reddit announcements feature, you have to set `enableRedditAnnouncements` in the
`config.json` to `false`.


## Features
* Modular system for commands
* Help command that automatically scales
* Welcome messages
* Announcements for twitch.tv/democraciv
* Announcements for new post from reddit.com/r/democraciv
* Political party management
* Self-assignable role management
* Get summaries from Wikipedia
* Event Logging 

## Modules
You can add and remove modules by adding or removing them from `initial_extensions` in `client.py`.

Module | Description 
------------ | ------------- |
module.links | Collection of useful links for the game (Wiki, Constitution, political parties etc.)
module.about | Commands regarding the bot itself 
module.admin | Re-, un- and load modules and the config 
module.fun | `-whois` and `-say` commands | 
module.help | Scaling `-help` command 
module.guild | Configure various functions of this bot for your guild 
module.roles | Add or remove roles from you 
module.parties | Join and leave political parties 
module.time | Get the current time in a number of different timezones 
module.legislature | Useful commands for Legislators on the Democraciv guild, such as `-submit` for submitting new bills 
module.wikipedia | Search for a topic on wikipedia 
module.random | Common choice commands (Heads or Tails etc.) 
event.logging | Logs events (member joins/leaves etc.) to a specified channel |
event.error_handler | Handles internal erros 
event.reddit | Handles notifications when there's a new post on r/democraciv 
event.twitch | Handles notifications when twitch.tv/democraciv is live 

## Roadmap

#####Update 0.13.0 - The Performance & Stability Update

* Refactor client.py
* Introduce custom exceptions
* Introduce utils to save time & code
* Replace blocking libraries (praw, wikipedia) with aiohttp API calls


#####Update 0.14.0 - The SQL Update

* Add a PostgreSQL database
* Migrate `guilds.json`, `partes.json` and `last_reddit_post.json` to new database


#####Update 0.15.0 - The Unit Test Update

* Add unittests most things, but especially for functions that are not reliant on a connection to Discord
 

#####Update 0.16.0 - The Moderation Update

* Add a `module.moderation.py` module with `-kick`, `-ban` etc. commands

#####Update 0.16.0 - The Suggestions Update

* Add suggestions from the community
* **Refactor & Cleanup to prepare for 1.0.0 release**






## Democraciv Discord Server
Join the [Democraciv Discord Server](https://discord.gg/AK7dYMG) to see the bot in action.

---

Contact @DerJonas#8109 on Discord if you have any questions left.
