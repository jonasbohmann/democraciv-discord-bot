CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS guilds(
    id bigint UNIQUE PRIMARY KEY,
    welcome_enabled bool DEFAULT FALSE,
    welcome_message text,
    welcome_channel bigint,
    logging_enabled bool DEFAULT FALSE,
    logging_channel bigint,
    default_role_enabled bool DEFAULT FALSE,
    default_role_role bigint,
    tag_creation_allowed bool DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS guild_private_channels(
    guild_id bigint references guilds(id),
    channel_id bigint,
    UNIQUE (guild_id, channel_id)
);


CREATE TABLE IF NOT EXISTS selfroles(
    guild_id bigint references guilds(id),
    role_id bigint,
    join_message text,
    UNIQUE (guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS youtube_uploads(
    id text UNIQUE
);

CREATE TABLE IF NOT EXISTS youtube_streams(
    id text UNIQUE
);

DO $$ BEGIN
    CREATE TYPE party_join_mode AS ENUM ('Public', 'Request', 'Private');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;


CREATE TABLE IF NOT EXISTS parties(
    id bigint UNIQUE PRIMARY KEY,
    discord_invite text,
    join_mode party_join_mode DEFAULT 'Public'::party_join_mode
);

CREATE TABLE IF NOT EXISTS party_leader(
    id serial UNIQUE PRIMARY KEY,
    party_id bigint references parties(id),
    leader_id bigint,
    UNIQUE (party_id, leader_id)
);

CREATE TABLE IF NOT EXISTS party_join_request(
    id serial UNIQUE PRIMARY KEY,
    party_id bigint references parties(id) ON DELETE CASCADE,
    requesting_member bigint
);

CREATE TABLE IF NOT EXISTS party_join_request_message(
    request_id serial references party_join_request(id) ON DELETE CASCADE,
    message_id bigint
);

CREATE TABLE IF NOT EXISTS party_alias(
    party_id bigint references parties(id) ON DELETE CASCADE,
    alias text UNIQUE
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

CREATE TABLE IF NOT EXISTS bills(
    id serial UNIQUE PRIMARY KEY,
    leg_session serial references legislature_sessions(id),
    name text,
    link text,
    tiny_link text,
    submitter bigint,
    submitter_description text,
    google_docs_description text,
    is_vetoable bool,
    status int DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bill_history(
    id serial UNIQUE PRIMARY KEY,
    bill_id serial references bills(id) ON DELETE CASCADE,
    date timestamp WITHOUT TIME ZONE,
    before_status int,
    after_status int
);


CREATE TABLE IF NOT EXISTS bill_lookup_tags(
    id serial UNIQUE PRIMARY KEY,
    bill_id serial references bills(id) ON DELETE CASCADE,
    tag text,
    UNIQUE (bill_id, tag)
);

CREATE TABLE IF NOT EXISTS legislature_motions(
    id serial UNIQUE PRIMARY KEY,
    leg_session serial references legislature_sessions(id),
    title text,
    description text,
    hastebin text,
    submitter bigint
);

CREATE INDEX IF NOT EXISTS bill_tags_tag_trgm_idx ON bill_tags USING gin (tag gin_trgm_ops);
CREATE INDEX IF NOT EXISTS bills_name_lower_idx ON bills (LOWER(bill_name));


CREATE TABLE IF NOT EXISTS guild_tags(
    guild_id bigint references guilds(id),
    id serial UNIQUE,
    name text,
    title text,
    content text,
    global bool DEFAULT FALSE,
    author bigint,
    uses int DEFAULT 0,
    is_embedded bool DEFAULT TRUE,
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

CREATE TABLE IF NOT EXISTS profile(
    user_id bigint PRIMARY KEY,
    description text
);

CREATE TABLE IF NOT EXISTS profile_mks(
    user_id bigint references profile(user_id),
    mk int,
    UNIQUE (user_id, mk)
);

CREATE TABLE IF NOT EXISTS dm_settings(
    user_id bigint PRIMARY KEY,
    ban_kick_mute bool DEFAULT TRUE,
    leg_session_open bool DEFAULT TRUE,
    leg_session_update bool DEFAULT TRUE,
    leg_session_submit bool DEFAULT TRUE,
    leg_session_withdraw bool DEFAULT TRUE,
    party_join_leave bool DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS starboard_entries(
    id serial PRIMARY KEY,
    author_id bigint,
    message_id bigint UNIQUE,
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