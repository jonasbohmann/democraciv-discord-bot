CREATE EXTENSION IF NOT EXISTS pg_trgm;

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
    role_id bigint,
    role_name text,
    join_message text
);

CREATE TABLE IF NOT EXISTS reddit_posts(
    id text UNIQUE
);

CREATE TABLE IF NOT EXISTS youtube_uploads(
    id text UNIQUE
);

CREATE TABLE IF NOT EXISTS youtube_streams(
    id text UNIQUE
);

CREATE TABLE IF NOT EXISTS twitch_streams(
    id text UNIQUE,
    has_sent_mod_reminder bool,
    has_sent_exec_reminder bool
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
);

CREATE TABLE IF NOT EXISTS legislature_sessions(
    id int UNIQUE PRIMARY KEY,
    speaker bigint,
    is_active bool,
    status text,
    vote_form text,
    start_unixtime bigint,
    voting_start_unixtime bigint,
    end_unixtime bigint
);

CREATE TABLE IF NOT EXISTS legislature_bills(
    id int UNIQUE PRIMARY KEY,
    leg_session int references legislature_sessions(id),
    link text UNIQUE,
    tiny_link text UNIQUE,
    bill_name text,
    description text,
    submitter bigint,
    is_vetoable bool,
    voted_on_by_leg bool,
    has_passed_leg bool,
    voted_on_by_ministry bool,
    has_passed_ministry bool
);

CREATE TABLE IF NOT EXISTS legislature_laws(
    bill_id int UNIQUE references legislature_bills(id),
    law_id int UNIQUE PRIMARY KEY,
    description text
);

CREATE TABLE IF NOT EXISTS legislature_tags(
    id int references legislature_laws(law_id) ON DELETE CASCADE,
    tag text
);

CREATE INDEX ON legislature_tags USING gin (tag gin_trgm_ops);

CREATE TABLE IF NOT EXISTS legislature_motions(
    id int UNIQUE PRIMARY KEY,
    leg_session int references legislature_sessions(id),
    title text,
    description text,
    submitter bigint
);

CREATE TABLE IF NOT EXISTS guild_tags(
    guild_id bigint references guilds(id),
    id serial UNIQUE PRIMARY KEY,
    name text,
    content text
);

CREATE TABLE IF NOT EXISTS guild_tags_alias(
    guild_tag_id serial references guild_tags(id),
    alias text
);
