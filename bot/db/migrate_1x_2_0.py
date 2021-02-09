import asyncio
import asyncpg


async def main():
    old_db = await asyncpg.create_pool("postgres://jonas:ehrenbruder@localhost/democraciv")
    new_db = await asyncpg.create_pool("postgres://jonas:ehrenbruder@localhost/dciv_two")

    guilds = await old_db.fetch("SELECT * FROM guilds")

    async with new_db.acquire() as connection:
        async with connection.transaction():
            for grecord in guilds:
                await connection.execute(
                    "INSERT INTO guild (id, welcome_enabled, welcome_message, welcome_channel, logging_enabled, logging_channel, default_role_enabled, default_role_role, tag_creation_allowed) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
                    grecord["id"],
                    grecord["welcome"],
                    grecord["welcome_message"],
                    grecord["welcome_channel"],
                    grecord["logging"],
                    grecord["logging_channel"],
                    grecord["defaultrole"],
                    grecord["defaultrole_role"],
                    grecord["tag_creation_allowed"],
                )

                for chan in grecord["logging_excluded"]:
                    await connection.execute(
                        "INSERT INTO guild_private_channel (guild_id, channel_id) VALUES ($1, $2)", grecord["id"], chan
                    )

                print(f"Guild {grecord['id']} added.")

            selfroles = await old_db.fetch("SELECT * FROM roles")

            for srecord in selfroles:
                await connection.execute(
                    "INSERT INTO selfrole (guild_id, role_id, join_message) VALUES ($1, $2, $3)",
                    srecord["guild_id"],
                    srecord["role_id"],
                    srecord["join_message"],
                )

                print(f"Selfrole {srecord['role_id']} added.")

            tags = await old_db.fetch("SELECT * FROM guild_tags")

            for tr in tags:
                t_id = await connection.fetchval(
                    "INSERT INTO tag (guild_id, name, title, content, global, author, uses, is_embedded) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id",
                    tr["guild_id"],
                    tr["name"],
                    tr["title"],
                    tr["content"],
                    tr["global"],
                    tr["author"],
                    tr["uses"],
                    tr["is_embedded"],
                )

                alias = await old_db.fetch("SELECT * from guild_tags_alias WHERE tag_id = $1", tr["id"])

                for al in alias:
                    await connection.execute(
                        "INSERT INTO tag_lookup (tag_id, alias) VALUES ($1, $2)", t_id, al["alias"]
                    )

                print(f"Tag '-{tr['name']}' added.")

            join_date = await old_db.fetch("SELECT * FROM original_join_dates")

            for jr in join_date:
                await connection.execute(
                    "INSERT INTO original_join_date (member, join_date, join_position) VALUES ($1, $2, $3)",
                    jr["member"],
                    jr["join_date"],
                    jr["join_position"],
                )

                print(f"Join date for {jr['member']} added.")

            stars = await old_db.fetch("SELECT * FROM starboard_entries")

            for sr in stars:
                e_id = await connection.fetchval(
                    "INSERT INTO starboard_entry (author_id, message_id, channel_id, guild_id, "
                    "message_jump_url, message_creation_date, is_posted_to_reddit, "
                    "starboard_message_id, starboard_message_created_at) VALUES ("
                    "$1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id",
                    sr["author_id"],
                    sr["message_id"],
                    sr["channel_id"],
                    sr["guild_id"],
                    sr["message_jump_url"],
                    sr["message_creation_date"],
                    sr["is_posted_to_reddit"],
                    sr["starboard_message_id"],
                    sr["starboard_message_created_at"],
                )

                starr = await old_db.fetch("SELECT * FROM starboard_starrers WHERE entry_id = $1", sr["id"])

                for s in starr:
                    await connection.execute(
                        "INSERT INTO starboard_starrer (entry_id, starrer_id) VALUES ($1, $2)", e_id, s["starrer_id"]
                    )

                print(f"Starboard entry {e_id} added.")


if __name__ == "__main__":
    print("Starting.")
    asyncio.run(main())
    print("All done.")
