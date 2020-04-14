CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS guilds(
    id bigint UNIQUE PRIMARY KEY,
    welcome bool DEFAULT FALSE,
    welcome_message text,
    welcome_channel bigint,
    logging bool DEFAULT FALSE,
    logging_channel bigint,
    logging_excluded bigint[] DEFAULT '{}',
    defaultrole bool DEFAULT FALSE,
    defaultrole_role bigint,
    tag_creation_allowed bool DEFAULT FALSE
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
    id text UNIQUE
);

CREATE TABLE IF NOT EXISTS parties(
    id bigint UNIQUE PRIMARY KEY,
    discord_invite text,
    is_private bool DEFAULT FALSE,
    leader bigint
);

CREATE TABLE IF NOT EXISTS party_alias(
    alias text UNIQUE,
    party_id bigint references parties(id)
);

DO $$ BEGIN
    CREATE TYPE session_status AS ENUM ('Submission Period', 'Voting Period', 'Closed');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

CREATE TABLE IF NOT EXISTS legislature_sessions(
    id serial UNIQUE PRIMARY KEY,
    speaker bigint,
    is_active bool,
    status session_status DEFAULT 'Submission Period'::session_status,
    vote_form text,
    opened_on timestamp WITHOUT TIME ZONE,
    voting_started_on timestamp WITHOUT TIME ZONE,
    closed_on timestamp WITHOUT TIME ZONE
);

CREATE TABLE IF NOT EXISTS legislature_bills(
    id serial UNIQUE PRIMARY KEY,
    leg_session serial references legislature_sessions(id),
    link text UNIQUE,
    tiny_link text UNIQUE,
    bill_name text,
    description text,
    google_docs_description text,
    submitter bigint,
    is_vetoable bool,
    voted_on_by_leg bool DEFAULT FALSE,
    has_passed_leg bool DEFAULT FALSE,
    voted_on_by_ministry bool DEFAULT FALSE,
    has_passed_ministry bool DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS legislature_laws(
    bill_id serial UNIQUE references legislature_bills(id),
    law_id serial UNIQUE PRIMARY KEY,
    passed_on timestamp WITHOUT TIME ZONE
);

CREATE TABLE IF NOT EXISTS legislature_tags(
    id serial references legislature_laws(law_id) ON DELETE CASCADE,
    tag text,
    UNIQUE (id, tag)
);

CREATE INDEX IF NOT EXISTS legislature_tags_tag_trgm_idx ON legislature_tags USING gin (tag gin_trgm_ops);
CREATE INDEX IF NOT EXISTS legislature_bills_name_lower_idx ON legislature_bills (LOWER(bill_name));

CREATE TABLE IF NOT EXISTS legislature_motions(
    id serial UNIQUE PRIMARY KEY,
    leg_session serial references legislature_sessions(id),
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

CREATE INDEX IF NOT EXISTS guild_tags_alias_alias_idx ON guild_tags_alias (alias);
CREATE UNIQUE INDEX IF NOT EXISTS guild_tags_alias_alias_guild_id_idx ON guild_tags_alias (alias, guild_id);


CREATE TABLE IF NOT EXISTS original_join_dates(
    member bigint UNIQUE,
    join_date timestamp WITHOUT TIME ZONE,
    join_position serial UNIQUE
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
    message_creation_date timestamp WITHOUT TIME ZONE,
    is_posted_to_reddit bool DEFAULT FALSE,
    starboard_message_id bigint UNIQUE,
    starboard_message_created_at timestamp
);

CREATE TABLE IF NOT EXISTS starboard_starrers(
    id serial PRIMARY KEY,
    entry_id serial references starboard_entries(id) ON DELETE CASCADE,
    starrer_id bigint,
    UNIQUE (entry_id, starrer_id)
);