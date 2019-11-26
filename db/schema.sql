CREATE TABLE IF NOT EXISTS guilds(
    id bigint UNIQUE PRIMARY KEY,
    welcome bool,
    welcome_message text,
    welcome_channel bigint,
    logging bool,
    logging_channel bigint,
    logging_excluded bigint[],
    defaultrole bool,
    defaultrole_role bigint
);

CREATE TABLE IF NOT EXISTS roles(
    guild_id bigint references guilds(id),
    role bigint,
    join_message text
);

CREATE TABLE IF NOT EXISTS reddit_posts(
    id text UNIQUE
);

CREATE TABLE IF NOT EXISTS parties(
    id bigint UNIQUE PRIMARY KEY,
    discord text,
    private bool,
    leader bigint
);

CREATE TABLE IF NOT EXISTS party_alias(
    alias text,
    party_id bigint references parties(id)
)
