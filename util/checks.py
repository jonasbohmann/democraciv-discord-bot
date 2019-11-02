import config


def checkIfOnDemocracivGuild(client, guild_id):
    print(f"{type(guild_id)} ++ {guild_id}")

    dciv_guild = client.get_guild(int(config.getConfig()["democracivServerID"]))

    print(f"{type(dciv_guild.id)} ++ {dciv_guild.id}")

    return dciv_guild.id == guild_id


if __name__ == '__main__':
    pass
