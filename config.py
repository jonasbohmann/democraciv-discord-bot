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


def dumpConfigParties():
    with open(filename3, 'w') as myfile:
        json.dump(config_parties, myfile, indent=2)


async def addParty(guild, invite, party: str):
    """Adds the inputted party paired with the invite, returns if the party was successfully added"""

    capsParty = string.capwords(party)
    # If the party already ready exists, return False
    if capsParty in config_parties['parties'] or capsParty in config_parties['capwordParties']:
        return False
    # Otherwise, create the party
    else:
        if capsParty == party:
            config_parties['parties'][capsParty] = invite
        else:
            config_parties['capwordParties'][capsParty] = party
            config_parties['parties'][party] = invite
        
        dumpConfigParties()
        await guild.create_role(name=party)
    return True


async def deleteParty(guild, party: str):
    """Deletes the inputted party, returns if the party was successfully deleted"""

    capsParty = string.capwords(party)
    # If the party already exists, delete it
    if capsParty in config_parties['parties'] or capsParty in config_parties['capwordParties']:
        if capsParty in config_parties['parties']:
            role = discord.utils.get(guild.roles, name=capsParty)
            # If the party has a role, delete the role
            if role != None:
                await role.delete()
            
            del config_parties['parties'][capsParty]
        elif capsParty in config_parties['capwordParties']:
            role = discord.utils.get(guild.roles, name=config_parties['capwordParties'][capsParty])
            if role != None:
                await role.delete()
            
            del config_parties['parties'][config_parties['capwordParties'][capsParty]]
            del config_parties['capwordParties'][capsParty]
        
        dumpConfigParties()
    # Otherwise return False
    else:
        return False
    return True
    

if __name__ == '__main__':
    print('Excuse me?')
