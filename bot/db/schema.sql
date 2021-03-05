CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS guild(
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

CREATE TABLE IF NOT EXISTS guild_private_channel(
    id serial UNIQUE PRIMARY KEY,
    guild_id bigint references guild(id) NOT NULL,
    channel_id bigint NOT NULL,
    UNIQUE (guild_id, channel_id)
);


CREATE TABLE IF NOT EXISTS selfrole(
    id serial UNIQUE PRIMARY KEY,
    guild_id bigint references guild(id) NOT NULL,
    role_id bigint NOT NULL,
    join_message text NOT NULL,
    UNIQUE (guild_id, role_id)
);

DO $$ BEGIN
    CREATE TYPE party_join_mode AS ENUM ('Public', 'Request', 'Private');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;


CREATE TABLE IF NOT EXISTS party(
    id bigint UNIQUE PRIMARY KEY,
    discord_invite text,
    join_mode party_join_mode DEFAULT 'Public'::party_join_mode NOT NULL
);

CREATE TABLE IF NOT EXISTS party_leader(
    id serial UNIQUE PRIMARY KEY,
    party_id bigint references party(id) NOT NULL,
    leader_id bigint NOT NULL,
    UNIQUE (party_id, leader_id)
);

CREATE TABLE IF NOT EXISTS party_join_request(
    id serial UNIQUE PRIMARY KEY,
    party_id bigint references party(id) ON DELETE CASCADE NOT NULL,
    requesting_member bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS party_join_request_message(
    id serial UNIQUE PRIMARY KEY,
    request_id serial references party_join_request(id) ON DELETE CASCADE NOT NULL,
    message_id bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS party_alias(
    id serial UNIQUE PRIMARY KEY,
    party_id bigint references party(id) ON DELETE CASCADE NOT NULL,
    alias text UNIQUE NOT NULL
);

DO $$ BEGIN
    CREATE TYPE session_status AS ENUM ('Submission Period', 'Voting Period', 'Closed');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

CREATE TABLE IF NOT EXISTS legislature_session(
    id serial UNIQUE PRIMARY KEY,
    speaker bigint NOT NULL,
    is_active bool DEFAULT true NOT NULL,
    status session_status DEFAULT 'Submission Period'::session_status NOT NULL,
    vote_form text,
    opened_on timestamp WITHOUT TIME ZONE NOT NULL,
    voting_started_on timestamp WITHOUT TIME ZONE,
    closed_on timestamp WITHOUT TIME ZONE
);

CREATE TABLE IF NOT EXISTS bill(
    id serial UNIQUE PRIMARY KEY,
    leg_session serial references legislature_session(id) NOT NULL,
    name text NOT NULL,
    link text NOT NULL,
    tiny_link text NOT NULL,
    submitter bigint NOT NULL,
    submitter_description text NOT NULL,
    is_vetoable bool NOT NULL,
    status int DEFAULT 0 NOT NULL
);

CREATE TABLE IF NOT EXISTS bill_sponsor(
    id serial UNIQUE PRIMARY KEY,
    bill_id serial references bill(id) ON DELETE CASCADE,
    sponsor bigint NOT NULL,
    UNIQUE (bill_id, sponsor)
);

CREATE TABLE IF NOT EXISTS bill_history(
    id serial UNIQUE PRIMARY KEY,
    bill_id serial references bill(id) ON DELETE CASCADE,
    date timestamp WITHOUT TIME ZONE,
    before_status int,
    after_status int
);


CREATE TABLE IF NOT EXISTS bill_lookup_tag(
    id serial UNIQUE PRIMARY KEY,
    bill_id serial references bill(id) ON DELETE CASCADE NOT NULL,
    tag text NOT NULL,
    UNIQUE (bill_id, tag)
);

CREATE TABLE IF NOT EXISTS motion(
    id serial UNIQUE PRIMARY KEY,
    leg_session serial references legislature_session(id),
    title text NOT NULL,
    description text NOT NULL,
    paste_link text NOT NULL,
    submitter bigint NOT NULL
);

CREATE INDEX IF NOT EXISTS bill_lookup_tag_tag_trgm_idx ON bill_lookup_tag USING gin (tag gin_trgm_ops);
CREATE INDEX IF NOT EXISTS bill_name_lower_idx ON bill (LOWER(name));


CREATE TABLE IF NOT EXISTS tag(
    id serial UNIQUE PRIMARY KEY,
    guild_id bigint references guild(id),
    name text NOT NULL,
    title text NOT NULL,
    content text NOT NULL,
    global bool DEFAULT FALSE NOT NULL,
    author bigint NOT NULL,
    uses int DEFAULT 0 NOT NULL,
    is_embedded bool DEFAULT TRUE NOT NULL,
    UNIQUE (guild_id, name)
);

CREATE TABLE IF NOT EXISTS tag_lookup(
    id serial UNIQUE PRIMARY KEY,
    tag_id serial references tag(id) ON DELETE CASCADE NOT NULL,
    alias text NOT NULL,
    UNIQUE (tag_id, alias)
);

CREATE INDEX IF NOT EXISTS tag_lookup_alias_idx ON tag_lookup (alias);


CREATE TABLE IF NOT EXISTS original_join_date(
    member bigint UNIQUE PRIMARY KEY,
    join_date timestamp WITHOUT TIME ZONE NOT NULL,
    join_position serial UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS profile(
    user_id bigint PRIMARY KEY NOT NULL,
    description text NOT NULL
);

CREATE TABLE IF NOT EXISTS profile_mk(
    id serial UNIQUE PRIMARY KEY,
    user_id bigint references profile(user_id) NOT NULL,
    mk int NOT NULL,
    UNIQUE (user_id, mk)
);

CREATE TABLE IF NOT EXISTS dm_setting(
    user_id bigint PRIMARY KEY,
    ban_kick_mute bool DEFAULT TRUE NOT NULL,
    leg_session_open bool DEFAULT TRUE NOT NULL,
    leg_session_update bool DEFAULT TRUE NOT NULL,
    leg_session_submit bool DEFAULT TRUE NOT NULL,
    leg_session_withdraw bool DEFAULT TRUE NOT NULL,
    party_join_leave bool DEFAULT TRUE NOT NULL
);

CREATE TABLE IF NOT EXISTS npc(
    id serial PRIMARY KEY,
    name text NOT NULL,
    avatar_url text,
    owner_id bigint NOT NULL,
    trigger_phrase text NOT NULL,
    UNIQUE (owner_id, trigger_phrase),
    UNIQUE (owner_id, name)
);

CREATE TABLE IF NOT EXISTS npc_allowed_user(
    id serial PRIMARY KEY,
    npc_id serial references npc(id) ON DELETE CASCADE,
    user_id bigint NOT NULL,
    UNIQUE (npc_id, user_id)
);

CREATE TABLE IF NOT EXISTS npc_automatic_mode(
    id serial PRIMARY KEY,
    npc_id serial references npc(id) ON DELETE CASCADE,
    user_id bigint NOT NULL,
    channel_id bigint NOT NULL,
    guild_id bigint NOT NULL,
    UNIQUE (npc_id, user_id, channeL_id)
);


CREATE TABLE IF NOT EXISTS npc_webhook(
    guild_id bigint NOT NULL,
    channel_id bigint PRIMARY KEY NOT NULL,
    webhook_id bigint NOT NULL,
    webhook_token text NOT NULL
);

CREATE TABLE IF NOT EXISTS starboard_entry(
    id serial PRIMARY KEY,
    author_id bigint,
    message_id bigint UNIQUE,
    channel_id bigint,
    guild_id bigint,
    message_jump_url text,
    message_creation_date timestamp WITHOUT TIME ZONE,
    is_posted_to_reddit bool DEFAULT FALSE,
    starboard_message_id bigint UNIQUE,
    starboard_message_created_at timestamp
);

CREATE TABLE IF NOT EXISTS starboard_starrer(
    id serial PRIMARY KEY,
    entry_id serial references starboard_entry(id) ON DELETE CASCADE,
    starrer_id bigint,
    UNIQUE (entry_id, starrer_id)
);