import discord


"""Democraciv MK specific objects names or roles & channels of government officials as well"""

# Static
MODERATION_TEAM_CHANNEL = 423938668710068224

def get_moderation_team_channel(bot):
    return bot.get_channel(MODERATION_TEAM_CHANNEL)



