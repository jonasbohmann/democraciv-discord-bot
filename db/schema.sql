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
    bill_name text,
    submitter bigint,
    is_vetoable bool,
    has_passed_leg bool,
    has_passed_ministry bool,
    is_law bool
);

CREATE TABLE IF NOT EXISTS legislature_motions(
    id int UNIQUE PRIMARY KEY,
    leg_session int references legislature_sessions(id),
    title text,
    description text,
    submitter bigint
);
