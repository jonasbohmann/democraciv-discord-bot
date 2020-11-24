import asyncio
import asyncpg

from bot.config import token

"""Simple script to convert database from 0.16.x to 0.17.0"""


async def get_db():
    return await asyncpg.create_pool(
        user=token.POSTGRESQL_USER,
        password=token.POSTGRESQL_PASSWORD,
        database=token.POSTGRESQL_DATABASE,
        host=token.POSTGRESQL_HOST,
    )


async def main():
    db = await get_db()

    async with db.acquire() as connection:
        async with connection.transaction():
            # Add defaults to guild
            await connection.execute("ALTER TABLE guilds ALTER welcome SET DEFAULT false;")
            await connection.execute("ALTER TABLE guilds ALTER logging SET DEFAULT false;")
            await connection.execute("ALTER TABLE guilds ALTER defaultrole SET DEFAULT false;")
            await connection.execute("ALTER TABLE guilds ALTER logging_excluded SET DEFAULT '{}';")
            print("Added defaults to guilds table.")

            # Fix parties new column names
            await connection.execute("ALTER TABLE parties RENAME COLUMN discord TO discord_invite;")
            await connection.execute("ALTER TABLE parties RENAME COLUMN private TO is_private;")
            await connection.execute("ALTER TABLE parties ALTER COLUMN is_private SET DEFAULT false;")
            print("Renamed columns in parties table.")

            # Fix legislature_session
            await connection.execute(
                """DO $$ BEGIN
                                CREATE TYPE session_status AS ENUM ('Submission Period', 'Voting Period', 'Closed');
                            EXCEPTION
                                WHEN duplicate_object THEN null;
                            END $$;"""
            )

            last_leg_session = await connection.fetchval("SELECT MAX(id) from legislature_sessions;")
            await connection.execute(
                f"""CREATE SEQUENCE legislature_sessions_seq START WITH {last_leg_session + 1};
                                     ALTER TABLE legislature_sessions ALTER COLUMN id SET DEFAULT nextval('legislature_sessions_seq'); 
                                     ALTER SEQUENCE legislature_sessions_seq OWNED BY legislature_sessions.id;"""
            )
            # await connection.execute(
            #   "ALTER TABLE legislature_sessions ALTER COLUMN status SET DATA TYPE session_status;")
            # await connection.execute(
            #   "ALTER TABLE legislature_sessions ALTER COLUMN status SET DEFAULT 'Submission Period'::session_status;")
            await connection.execute("ALTER TABLE legislature_sessions RENAME COLUMN start_unixtime TO opened_on;")
            await connection.execute(
                "ALTER TABLE legislature_sessions RENAME COLUMN voting_start_unixtime TO voting_started_on;"
            )
            await connection.execute("ALTER TABLE legislature_sessions RENAME COLUMN end_unixtime TO closed_on;")

            await connection.execute(
                "ALTER TABLE legislature_sessions ALTER COLUMN opened_on SET DATA TYPE timestamp "
                "WITHOUT TIME ZONE USING to_timestamp(opened_on)::timestamp without time zone;"
            )
            await connection.execute(
                "ALTER TABLE legislature_sessions ALTER COLUMN voting_started_on SET DATA TYPE "
                "timestamp WITHOUT TIME ZONE USING to_timestamp(voting_started_on)::timestamp without time zone;"
            )
            await connection.execute(
                "ALTER TABLE legislature_sessions ALTER COLUMN closed_on SET DATA TYPE timestamp "
                "WITHOUT TIME ZONE USING to_timestamp(closed_on)::timestamp without time zone;"
            )

            print("Added serial and converted unixtime -> timestamp in legislature_sessions.")

            # legislature_bills
            await connection.execute("ALTER TABLE legislature_bills ALTER COLUMN voted_on_by_leg SET DEFAULT false;")
            await connection.execute("ALTER TABLE legislature_bills ALTER COLUMN has_passed_leg SET DEFAULT false;")
            await connection.execute(
                "ALTER TABLE legislature_bills ALTER COLUMN voted_on_by_ministry SET DEFAULT false;"
            )
            await connection.execute(
                "ALTER TABLE legislature_bills ALTER COLUMN has_passed_ministry SET DEFAULT false;"
            )
            last_bill = await connection.fetchval("SELECT MAX(id) from legislature_bills;")
            await connection.execute(
                f"""CREATE SEQUENCE legislature_bills_seq START WITH {last_bill + 1};
                                        ALTER TABLE legislature_bills ALTER COLUMN id SET DEFAULT nextval('legislature_bills_seq'); 
                                        ALTER SEQUENCE legislature_bills_seq OWNED BY legislature_bills.id;"""
            )

            print("Added serial and new defaults to legislature_bills.")

            # legislature_laws
            last_law = await connection.fetchval("SELECT MAX(law_id) from legislature_laws;")
            await connection.execute(
                f"""CREATE SEQUENCE legislature_laws_seq START WITH {last_law + 1};
                                        ALTER TABLE legislature_laws ALTER COLUMN law_id SET DEFAULT nextval('legislature_laws_seq'); 
                                        ALTER SEQUENCE legislature_laws_seq OWNED BY legislature_laws.law_id;"""
            )
            await connection.execute("ALTER TABLE legislature_laws ADD COLUMN passed_on timestamp WITHOUT TIME ZONE;")

            print("Added serial and passed_on column to legislature_laws.")

            # legislature_tags
            # await connection.execute("ALTER TABLE legislature_tags ADD UNIQUE (id, tag);")

            print("Added unqiue constraint to legislature_tags.")

            # legislature_motions
            last_motion = await connection.fetchval("SELECT MAX(id) from legislature_motions;")
            await connection.execute(
                f"""CREATE SEQUENCE legislature_motions_seq START WITH {last_motion + 1};
                                        ALTER TABLE legislature_motions ALTER COLUMN id SET DEFAULT nextval('legislature_motions_seq'); 
                                        ALTER SEQUENCE legislature_motions_seq OWNED BY legislature_motions.id;"""
            )
            print("Added serial to legislature_motions.")

            # tags
            await connection.execute("ALTER TABLE guild_tags ALTER COLUMN global SET DEFAULT false;")
            await connection.execute("ALTER TABLE guild_tags_alias ADD COLUMN global bool;")
            await connection.execute("ALTER TABLE guild_tags_alias ALTER COLUMN global SET DEFAULT false;")

            tags = await connection.fetch("SELECT * FROM guild_tags")

            for tag in tags:
                await connection.execute(
                    "UPDATE guild_tags_alias SET global = $1 WHERE tag_id = $2",
                    tag["global"],
                    tag["id"],
                )

            print("Added global column to guild_tags_alias and set new defaults.")


if __name__ == "__main__":
    asyncio.run(main())
    print("Migration complete.")
