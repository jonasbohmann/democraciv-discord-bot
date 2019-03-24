## democraciv-bot
Discord Bot for r/Democraciv written in Python 3. Provides useful information, political party management and more. 

## Requirements
* [Python](https://www.python.org/downloads//) 3.6 or higher
* [discord.py-rewrite](https://github.com/Rapptz/discord.py/tree/3f06f247c039a23948e7bb0014ea31db533b4ba2) commit 3f06f24
* [wikipedia](https://pypi.org/project/wikipedia/) 1.4.0 or higher
* [python-twitch-client](https://github.com/tsifrer/python-twitch-client) 0.6.0 or higher
* [praw](https://github.com/praw-dev/praw) latest available version
 

See `requirements.txt` for details.

## Features
* Modular system for commands
* Help command that automatically scales
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
module.role | Join and leave political parties | ✅
module.time | Get current time in different timezones | ✅
module.wikipedia | Search for a topic on wikipedia | ✅
event.logging | Logs events (member joins/leaves etc.) to a specified channel | 
event.error_handler | Handles internal erros | 

## Planned
* SQL Database for seperate configs per server
* Announcments for Twitch and Reddit posts
* Proportional Representation voting

## Democraciv Discord Server
Join the [Democraciv Discord Server](https://discord.gg/AK7dYMG) to see the bot in action.

---

Contact @DerJonas#8109 on Discord if you have any questions left.
