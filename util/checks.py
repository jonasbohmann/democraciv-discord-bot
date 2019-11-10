import config


def isDemocracivGuild(guild_id):
    return int(config.getConfig()["democracivServerID"]) == int(guild_id)


if __name__ == '__main__':
    pass
