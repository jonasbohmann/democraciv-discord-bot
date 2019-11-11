import os
import json
import string
import discord


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
# Script that handles the loading of the global_config.json.
# Throws error if the file is not found.
#


#    ATTENTION
#
#    config.py and the JSON configs will be deprecated in the near feature.
#    The bot will use a SQLite database instead, with aiosqlite as API.
#
#    as such, these ugly functions will not be refactored
#


def parseJSONFromFile(file_path):
    try:
        file_dir = os.path.dirname(os.path.realpath('__file__'))
        file_name = os.path.join(file_dir, file_path)
        return json.loads(open(file_name).read())
    except FileNotFoundError:
        print(f"ERROR - Couldn't find file: {file_path}")
        return None


# Load every config file into memory
config = parseJSONFromFile('config/global_config.json')
token = parseJSONFromFile('config/token.json')
config_parties = parseJSONFromFile('config/parties.json')
last_reddit_post = parseJSONFromFile('config/last_reddit_post.json')
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


# Guild dependant
def checkIfGuildExists(guild_id):
    guild_id = str(guild_id)

    for guild in getGuilds():
        if guild == guild_id:
            return True
    return False


def initializeNewGuild(guild: discord.Guild):
    if not checkIfGuildExists(str(guild.id)):
        payload = {"name": guild.name,
                   "config": {"enableWelcomeMessage": False, "welcomeChannel": "", "enableLogging": False,
                              "excludedChannelsFromLogging": [], "logChannel": ""},
                   "strings": {"welcomeMessage": ""},
                   "roles": {}
                   }

        getGuilds()[str(guild.id)] = payload

        with open(os.path.join(os.path.dirname(os.path.realpath('__file__')), 'config/guilds.json'), 'w') as file:
            json.dump(guilds, file, indent=4)

        return True

    else:
        print(f"ERROR - Could not initialize guild {guild.name}")
        return False


def getStrings(guild_id):
    guild_id = str(guild_id)

    if checkIfGuildExists(guild_id):
        return getGuilds()[guild_id]['strings']
    else:
        print(f'ERROR - In config.py could not find {guild_id}')
        return None


def getGuildConfig(guild_id):
    guild_id = str(guild_id)

    if checkIfGuildExists(guild_id):
        return getGuilds()[guild_id]['config']
    else:
        print(f'ERROR - In config.py could not find {guild_id}')
        return None


def getRoles(guild_id):
    guild_id = str(guild_id)

    if checkIfGuildExists(guild_id):
        return getGuilds()[guild_id]['roles']
    else:
        print(f'ERROR - In config.py could not find {guild_id}')
        return None


def addExcludedLogChannel(guild_id, channel_id):
    guild_id = str(guild_id)
    channel_id = str(channel_id)

    if checkIfGuildExists(guild_id):
        getGuildConfig(guild_id)['excludedChannelsFromLogging'].append(channel_id)
        with open(os.path.join(os.path.dirname(os.path.realpath('__file__')), 'config/guilds.json'), 'w') as file:
            json.dump(guilds, file, indent=4)
        return True
    else:
        print(f'ERROR - In config.py could not find {guild_id}')
        return False


def removeExcludedLogChannel(guild_id, channel_id):
    guild_id = str(guild_id)
    channel_id = str(channel_id)

    if checkIfGuildExists(guild_id):
        getGuildConfig(guild_id)['excludedChannelsFromLogging'].remove(channel_id)
        with open(os.path.join(os.path.dirname(os.path.realpath('__file__')), 'config/guilds.json'), 'w') as file:
            json.dump(guilds, file, indent=4)
        return True
    else:
        print(f'ERROR - In config.py could not find {guild_id}')
        return False


def setLoggingChannel(guild_id, channel):
    guild_id = str(guild_id)
    channel = str(channel)

    if checkIfGuildExists(guild_id):
        getGuildConfig(guild_id)["logChannel"] = channel
        with open(os.path.join(os.path.dirname(os.path.realpath('__file__')), 'config/guilds.json'), 'w') as file:
            json.dump(guilds, file, indent=4)
        return True
    else:
        print(f'ERROR - In config.py could not find {guild_id}')
        return False


def updateLoggingModule(guild_id, status: bool):
    guild_id = str(guild_id)

    if checkIfGuildExists(guild_id):
        # Enable module
        if status:
            getGuildConfig(guild_id)["enableLogging"] = True
            with open(os.path.join(os.path.dirname(os.path.realpath('__file__')), 'config/guilds.json'), 'w') as file:
                json.dump(guilds, file, indent=4)

        # Disable module
        if not status:
            getGuildConfig(guild_id)["enableLogging"] = False
            with open(os.path.join(os.path.dirname(os.path.realpath('__file__')), 'config/guilds.json'), 'w') as file:
                json.dump(guilds, file, indent=4)
    else:
        print(f'ERROR - In config.py could not find {guild_id}')
        return None


def updateWelcomeModule(guild_id, status: bool):
    guild_id = str(guild_id)

    if checkIfGuildExists(guild_id):
        # Enable module
        if status:
            getGuildConfig(guild_id)["enableWelcomeMessage"] = True
            with open(os.path.join(os.path.dirname(os.path.realpath('__file__')), 'config/guilds.json'), 'w') as file:
                json.dump(guilds, file, indent=4)

        # Disable module
        if not status:
            getGuildConfig(guild_id)["enableWelcomeMessage"] = False
            with open(os.path.join(os.path.dirname(os.path.realpath('__file__')), 'config/guilds.json'), 'w') as file:
                json.dump(guilds, file, indent=4)
    else:
        print(f'ERROR - In config.py could not find {guild_id}')
        return None


def setWelcomeChannel(guild_id, channel):
    guild_id = str(guild_id)
    channel = str(channel)

    if checkIfGuildExists(guild_id):
        getGuildConfig(guild_id)["welcomeChannel"] = channel
        with open(os.path.join(os.path.dirname(os.path.realpath('__file__')), 'config/guilds.json'), 'w') as file:
            json.dump(guilds, file, indent=4)
        return True
    else:
        print(f'ERROR - In config.py could not find {guild_id}')
        return False


def setWelcomeMessage(guild_id, message):
    guild_id = str(guild_id)

    if checkIfGuildExists(guild_id):
        getStrings(guild_id)["welcomeMessage"] = message
        with open(os.path.join(os.path.dirname(os.path.realpath('__file__')), 'config/guilds.json'), 'w') as file:
            json.dump(guilds, file, indent=4)
        return True
    else:
        print(f'ERROR - In config.py could not find {guild_id}')
        return False


def updateDefaultRole(guild_id, status: bool):
    guild_id = str(guild_id)

    if checkIfGuildExists(guild_id):
        # Enable module
        if status:
            getGuildConfig(guild_id)["enableDefaultRole"] = True
            with open(os.path.join(os.path.dirname(os.path.realpath('__file__')), 'config/guilds.json'), 'w') as file:
                json.dump(guilds, file, indent=4)

        # Disable module
        if not status:
            getGuildConfig(guild_id)["enableDefaultRole"] = False
            with open(os.path.join(os.path.dirname(os.path.realpath('__file__')), 'config/guilds.json'), 'w') as file:
                json.dump(guilds, file, indent=4)
    else:
        print(f'ERROR - In config.py could not find {guild_id}')
        return None


def setDefaultRole(guild_id, role):
    guild_id = str(guild_id)

    if checkIfGuildExists(guild_id):
        getGuildConfig(guild_id)["defaultRole"] = role
        with open(os.path.join(os.path.dirname(os.path.realpath('__file__')), 'config/guilds.json'), 'w') as file:
            json.dump(guilds, file, indent=4)
        return True
    else:
        print(f'ERROR - In config.py could not find {guild_id}')
        return False


# Dump JSON functions
def setLastRedditPost():
    with open(os.path.join(os.path.dirname(os.path.realpath('__file__')), 'config/last_reddit_post.json'), 'w') as file:
        json.dump(last_reddit_post, file, indent=1)


def dumpConfigParties():
    with open(os.path.join(os.path.dirname(os.path.realpath('__file__')), 'config/parties.json'), 'w') as file:
        json.dump(config_parties, file, indent=2)


def dumpConfigRoles(guild_id):
    guild_id = str(guild_id)

    with open(os.path.join(os.path.dirname(os.path.realpath('__file__')), 'config/guilds.json'), 'w') as file:
        json.dump(guilds, file, indent=4)


async def addRole(guild, join_message, role: str) -> str:
    """Adds the inputted role paired with the join message, returns an empty string if it was successfully added
    , otherwise returns error as string. """
    if role in getRoles(guild.id):
        return f'{role} already exists!'

    # Otherwise, create the role
    else:
        getRoles(guild.id)[role] = join_message

        dumpConfigRoles(guild.id)
        await guild.create_role(name=role)
    return ''


async def deleteRole(guild, role: str) -> str:
    """Deletes the inputted role, returns an empty string if it was successfully deleted,
    otherwise returns error as string. """
    # If the role already exists, delete it
    if role in getRoles(guild.id):
        discord_role = discord.utils.get(guild.roles, name=role)
        # If the role has a role, delete the role (lol)
        if role is not None:
            await discord_role.delete()
        del getRoles(guild.id)[role]

        dumpConfigRoles(guild.id)

    # Otherwise return False
    else:
        return f'{role} not found!'
    return ''


async def addParty(guild, invite, party: str) -> str:
    """Adds the inputted party paired with the invite, returns an empty string if it was successfully added,
    otherwise returns error as string. """
    if ',' in party:
        return f'May not have \',\' in party name!'

    caps_party = string.capwords(party)
    if caps_party in config_parties['parties']:
        return f'{caps_party} already exists!'
    elif caps_party in config_parties['aliases']:
        return f'{caps_party} is already an alias!'
    # Otherwise, create the party
    else:
        if caps_party == party:
            config_parties['parties'][caps_party] = invite
        else:
            config_parties['aliases'][caps_party] = party
            config_parties['parties'][party] = invite

        dumpConfigParties()
        await guild.create_role(name=party)
    return ''


async def deleteParty(guild, party: str) -> str:
    """Deletes the inputted party and related aliases, returns an empty string if it was successfully deleted,
    otherwise returns error as string. """

    caps_party = string.capwords(party)

    # If the given party name is actually an alias, return an error
    if caps_party in config_parties['aliases'] and string.capwords(config_parties['aliases'][caps_party]) != caps_party:
        return f'May not delete an alias! See `-deletealias`.'
    # If the party already exists, delete it
    if caps_party in config_parties['parties'] or caps_party in config_parties['aliases']:
        if caps_party in config_parties['parties']:
            role = discord.utils.get(guild.roles, name=party)
            # If the party has a role, delete the role
            if role is not None:
                await role.delete()

            del config_parties['parties'][caps_party]
        elif caps_party in config_parties['aliases']:
            role = discord.utils.get(guild.roles, name=config_parties['aliases'][caps_party])
            if role is not None:
                await role.delete()

            del config_parties['parties'][config_parties['aliases'][caps_party]]
            del config_parties['aliases'][caps_party]

        # Delete related aliases
        for alias in list(config_parties['aliases']):
            if config_parties['aliases'][alias] == party and alias != caps_party:
                del config_parties['aliases'][alias]

        dumpConfigParties()
    # Otherwise return False
    else:
        return f'{party} not found!'
    return ''


async def addPartyAlias(party: str, alias: str) -> str:
    """Added alias as a new alias to party, returns an empty string if it was successfully added, otherwise returns
    error as string. """
    caps_alias, party = string.capwords(alias), string.capwords(party)

    if party not in config_parties['parties'] and party not in config_parties['aliases']:
        return f'{party} not found!'
    elif alias in config_parties['parties'] or caps_alias in config_parties['parties']:
        return f'{caps_alias} is already the name of a party!'
    elif caps_alias in config_parties['aliases']:
        party = config_parties['aliases'][caps_alias]
        return f'{caps_alias} is already an alias for {party}!'
    else:
        # If party has unusual caps, fix caps
        if party not in config_parties['parties']:
            party = config_parties['aliases'][party]
        config_parties['aliases'][caps_alias] = party
        dumpConfigParties()

    return ''


async def deletePartyAlias(alias: str) -> str:
    """Deletes a party alias, returns an empty string if it was successfully deleted, otherwise returns error as
    string. """
    caps_alias = string.capwords(alias)
    if caps_alias not in config_parties['aliases']:
        return f'{alias} not found!'
    # Check if alias is a party name
    elif string.capwords(config_parties['aliases'][caps_alias]) == caps_alias:
        return 'May not delete party name!'
    else:
        del config_parties['aliases'][caps_alias]
        dumpConfigParties()

    return ''


if __name__ == '__main__':
    pass
