import os
import json


# -- Discord Bot for the r/Democraciv Server --
#
# Author: DerJonas
# Interpreter: Python3.7
# Library: discord.py 1.0.0a
# License: MIT
# Source: https://github.com/jonasbohmann/democraciv-discord-bot
#


# -- config.py --
#
# Script that handles the loading of the config.json.
# Throws error if the file is not found.
#


try:
    fileDir = os.path.dirname(os.path.realpath('__file__'))
    filename1 = os.path.join(fileDir, 'config/config.json')
    config = json.loads(open(filename1).read())
except FileNotFoundError:
    print("ERROR - Couldn't find config.json")


try:
    fileDir = os.path.dirname(os.path.realpath('__file__'))
    filename2 = os.path.join(fileDir, 'config/token.json')
    token = json.loads(open(filename2).read())
except FileNotFoundError:
    print("ERROR - Couldn't find token.json")


try:
    fileDir = os.path.dirname(os.path.realpath('__file__'))
    filename3 = os.path.join(fileDir, 'config/config_parties.json')
    config_parties = json.loads(open(filename3).read())
except FileNotFoundError:
    print("ERROR - Couldn't find config_parties.json")


def getToken():
    return token['token']


def getConfig():
    return config['config']


def getLinks():
    return config['links']


def getStrings():
    return config['strings']


def getCooldown():
    return config['config']['commandCooldown']


def getPrefix():
    return config['config']['prefix']


def getParties():
    return config_parties['parties']

def getCapwordParties():
    return config_parties['capwordParties']


def getReddit():
    return config['reddit']


def getTwitch():
    return config['twitch']


if __name__ == '__main__':
    print('Excuse me?')
