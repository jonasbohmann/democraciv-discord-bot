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
    alias text UNIQUE,
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
    hastebin text,
    submitter bigint
);

CREATE TABLE IF NOT EXISTS guild_tags(
    guild_id bigint references guilds(id),
    id serial UNIQUE,
    name text,
    title text,
    content text,
    global bool DEFAULT FALSE,
    author bigint,
    uses int DEFAULT 0,
    PRIMARY KEY (guild_id, id),
    UNIQUE (guild_id, name)
);

CREATE TABLE IF NOT EXISTS guild_tags_alias(
    tag_id serial references guild_tags(id) ON DELETE CASCADE,
    guild_id bigint references guilds(id),
    alias text,
    global bool DEFAULT FALSE,
    UNIQUE (guild_id, alias)
);

CREATE TABLE IF NOT EXISTS original_join_dates(
    member bigint UNIQUE,
    join_date timestamp,
    join_position int
);

CREATE TABLE IF NOT EXISTS starboard_entries(
    id serial PRIMARY KEY,
    author_id bigint,
    message_id bigint UNIQUE,
    message_jump_url text,
    message_content text,
    message_image_url text,
    channel_id bigint,
    guild_id bigint,
    message_creation_date timestamp,
    is_posted_to_reddit bool DEFAULT false,
    starboard_message_id bigint UNIQUE,
    starboard_message_created_at timestamp
);

CREATE TABLE IF NOT EXISTS starboard_starrers(
    id serial PRIMARY KEY,
    entry_id serial references starboard_entries(id) ON DELETE CASCADE,
    starrer_id bigint,
    UNIQUE (entry_id, starrer_id)
);