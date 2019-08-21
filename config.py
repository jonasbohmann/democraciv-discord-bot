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


async def addParty(guild, invite, party: str) -> str:
    """Adds the inputted party paired with the invite, returns an empty string if it was successfully added, otherwise returns error as string."""
    if ',' in party:
        return f'May not have \',\' in party name!'

    capsParty = string.capwords(party)
    if capsParty in config_parties['parties']:
        return f'{capsParty} already exists!'
    elif capsParty in config_parties['aliases']:
        return f'{capsParty} is already an alias!'
    # Otherwise, create the party
    else:
        if capsParty == party:
            config_parties['parties'][capsParty] = invite
        else:
            config_parties['aliases'][capsParty] = party
            config_parties['parties'][party] = invite

        dumpConfigParties()
        await guild.create_role(name=party)
    return ''


async def deleteParty(guild, party: str) -> str:
    """Deletes the inputted party and related aliases, returns an empty string if it was successfully deleted, otherwise returns error as string."""

    capsParty = string.capwords(party)

    # If the given party name is actually an alias, return an error
    if capsParty in config_parties['aliases'] and string.capwords(config_parties['aliases'][capsParty]) != capsParty:
        return f'May not delete an alias! See `-deletealias`.'
    # If the party already exists, delete it
    if capsParty in config_parties['parties'] or capsParty in config_parties['aliases']:
        if capsParty in config_parties['parties']:
            role = discord.utils.get(guild.roles, name=party)
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
        
        # Delete related aliases
        for alias in list(config_parties['aliases']):
            if config_parties['aliases'][alias] == party and alias != capsParty:
               del config_parties['aliases'][alias]

        dumpConfigParties()
    # Otherwise return False
    else:
        return f'{party} not found!'
    return ''


async def addPartyAlias(party: str, alias: str) -> str:
    """Added alias as a new alias to party, returns an empty string if it was successfully added, otherwise returns error as string."""
    capsAlias, party = string.capwords(alias), string.capwords(party)

    if party not in config_parties['parties'] and party not in config_parties['aliases']:
        return f'{party} not found!'
    elif alias in config_parties['parties'] or capsAlias in config_parties['parties']:
        return f'{capsAlias} is already the name of a party!'
    elif capsAlias in config_parties['aliases']:
        party = config_parties['aliases'][capsAlias]
        return f'{capsAlias} is already an alias for {party}!'
    else:
        # If party has unusual caps, fix caps
        if party not in config_parties['parties']:
            party = config_parties['aliases'][party]
        config_parties['aliases'][capsAlias] = party
        dumpConfigParties()

    return ''


async def deletePartyAlias(alias: str) -> str:
    """Deletes a party alias, returns an empty string if it was successfully deleted, otherwise returns error as string."""
    capsAlias = string.capwords(alias)
    if capsAlias not in config_parties['aliases']:
        return f'{alias} not found!'
    # Check if alias is a party name
    elif string.capwords(config_parties['aliases'][capsAlias]) == capsAlias:
        return 'May not delete party name!'
    else:
        del config_parties['aliases'][capsAlias]
        dumpConfigParties()
    
    return ''


if __name__ == '__main__':
    pass
