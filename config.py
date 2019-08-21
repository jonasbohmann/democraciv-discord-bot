import os
import json
import string
import discord

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

try:
    fileDir = os.path.dirname(os.path.realpath('__file__'))
    filename4 = os.path.join(fileDir, 'config/last_reddit_post.json')
    last_reddit_post = json.loads(open(filename4).read())
except FileNotFoundError:
    print("ERROR - Couldn't find last_reddit_post.json")


def getToken():
    return token['token']


def getTokenFile():
    return token


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


def getPartyAliases():
    return config_parties['aliases']


def getReddit():
    return config['reddit']


def getTwitch():
    return config['twitch']


def getLastRedditPost():
    return last_reddit_post


def setLastRedditPost():
    with open(filename4, 'w') as my_file:
        json.dump(last_reddit_post, my_file, indent=1)


def dumpConfigParties():
    with open(filename3, 'w') as myfile:
        json.dump(config_parties, myfile, indent=2)


async def addParty(guild, invite, party: str):
    """Adds the inputted party paired with the invite, returns if the party was successfully added"""

    capsParty = string.capwords(party)
    # If the party already ready exists, return False
    if capsParty in config_parties['parties'] or capsParty in config_parties['aliases']:
        return False
    # Otherwise, create the party
    else:
        if capsParty == party:
            config_parties['parties'][capsParty] = invite
        else:
            config_parties['aliases'][capsParty] = party
            config_parties['parties'][party] = invite

        dumpConfigParties()
        await guild.create_role(name=party)
    return True


async def deleteParty(guild, party: str):
    """Deletes the inputted party, returns if the party was successfully deleted"""

    capsParty = string.capwords(party)
    # If the party already exists, delete it
    if capsParty in config_parties['parties'] or capsParty in config_parties['aliases']:
        if capsParty in config_parties['parties']:
            role = discord.utils.get(guild.roles, name=capsParty)
            # If the party has a role, delete the role
            if role is not None:
                await role.delete()

            del config_parties['parties'][capsParty]
        elif capsParty in config_parties['aliases']:
            role = discord.utils.get(guild.roles, name=config_parties['aliases'][capsParty])
            if role is not None:
                await role.delete()

            del config_parties['parties'][config_parties['aliases'][capsParty]]
            del config_parties['aliases'][capsParty]

        dumpConfigParties()
    # Otherwise return False
    else:
        return False
    return True


async def addPartyAlias(party: str, alias: str) -> str:
    """Added alias as a new alias to party, returns an empty string if it was successfully added, otherwise returns error as string."""
    capsAlias = string.capwords(alias)
    if party not in config_parties['parties'] and string.capwords(party) not in config_parties['aliases']:
        return f'{party} not found!'
    elif alias in config_parties['parties'] or capsAlias in config_parties['parties']:
        return f'{alias} is already the name of a party!'
    elif capsAlias in config_parties['aliases']:
        party = config_parties['aliases'][capsAlias]
        return f'{alias} is already an alias for {party}!'
    else:
        config_parties['aliases'][capsAlias] = party
        dumpConfigParties()

    return ''


if __name__ == '__main__':
    pass
