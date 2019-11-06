import config


def checkIfOnDemocracivGuild(client, guild_id):
    dciv_guild = client.get_guild(int(config.getConfig()["democracivServerID"]))

    return dciv_guild.id == guild_id


if __name__ == '__main__':
    pass
