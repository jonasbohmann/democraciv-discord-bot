import os
import json

# -- Discord Bot for the r/Democraciv Server --
#
# Author: DerJonas
# Interpreter: Python3.7
# Library: discord.py
# License: MIT
# Source: https://github.com/jonasbohmann/democraciv-discord-bot
#


# -- config.py --
#
# Script that handles the loading of the config.json.
# Throws error if the file is not found.
#


#    ATTENTION
#
#    config.py and the JSON configs will be deprecated in the near feature.
#    The bot will use a PostgreSQL database instead
#
#    as such, these ugly functions will not be refactored
#


def parseJSONFromFile(file_path):
    try:
        file_dir = os.path.dirname(os.path.realpath(__file__))
        file_name = os.path.join(file_dir, file_path)
        return json.loads(open(file_name).read())
    except FileNotFoundError:
        print(f"ERROR - Couldn't find file: {file_path}")
        return None


# Load every config file into memory
config = parseJSONFromFile('config/config.json')
token = parseJSONFromFile('config/token.json')
config_parties = parseJSONFromFile('config/parties.json')
guilds = parseJSONFromFile('config/guilds.json')


def getToken():
    return token['token']


def getTokenFile():
    return token


def getConfigFile():
    return config


def getGuilds():
    return guilds['guilds']


def getConfig():
    return config['config']


def getPrefix():
    return config['config']['prefix']


def getLinks():
    return config['links']


def getCooldown():
    return config['config']['commandCooldown']


def getReddit():
    return config['reddit']


def getTwitch():
    return config['twitch']


if __name__ == '__main__':
    pass
