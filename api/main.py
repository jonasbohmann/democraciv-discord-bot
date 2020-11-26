import asyncio
import logging
import asyncpg
import pydantic
import xdice

from api.provider import RedditManager, TwitchManager
from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import PlainTextResponse

logging.basicConfig(level=logging.INFO)


class Database:
    def __init__(self, *, dsn):
        self.dsn = dsn
        self._loop = asyncio.get_event_loop()
        self.pool = None
        self.ready = False

    async def apply_schema(self):
        schema = """CREATE TABLE IF NOT EXISTS reddit_webhook(
                    id serial PRIMARY KEY,
                    subreddit text NOT NULL,
                    webhook_id bigint NOT NULL,
                    webhook_url text NOT NULL,
                    guild_id bigint NOT NULL,
                    channel_id bigint NOT NULL
                    );
                    
                    CREATE TABLE IF NOT EXISTS twitch_webhook(
                    id serial PRIMARY KEY,
                    streamer text NOT NULL,
                    webhook_id bigint NOT NULL,
                    webhook_url text NOT NULL,
                    guild_id bigint NOT NULL,
                    channel_id bigint NOT NULL,
                    everyone_ping bool DEFAULT FALSE NOT NULL
                    );
                    
                    CREATE TABLE IF NOT EXISTS reddit_post(
                    id text UNIQUE NOT NULL
                    );
                    
                    CREATE TABLE IF NOT EXISTS youtube_upload(
                    id text UNIQUE NOT NULL
                    );
                    
                    CREATE TABLE IF NOT EXISTS youtube_stream(
                    id text UNIQUE NOT NULL
                    );"""

        await self.pool.execute(schema)

    async def make_pool(self):
        self.pool = await asyncpg.create_pool(dsn=self.dsn, loop=self._loop)
        await self.apply_schema()
        self.ready = True
        return self.pool


app = FastAPI()
db = Database(dsn="postgres://postgres:ehre@localhost/api_test")
reddit_manager = RedditManager(db=db)
twitch_manager = TwitchManager(db=db)


class AddWebhook(pydantic.BaseModel):
    target: str
    webhook_url: str
    webhook_id: int
    guild_id: int
    channel_id: int


class AddTwitchHook(AddWebhook):
    everyone_ping: bool


class RemoveWebhook(pydantic.BaseModel):
    id: int
    guild_id: int


class ClearPerGuild(pydantic.BaseModel):
    guild_id: int


class Dice(pydantic.BaseModel):
    dices: str


@app.on_event("startup")
async def startup_event():
    await db.make_pool()
    logging.info("API ready to serve")


@app.get("/")
async def ok():
    return {"ok": "ok"}


@app.get("/reddit/list/{guild_id}")
async def reddit_list(guild_id: int):
    webhooks = await reddit_manager.get_webhooks_per_guild(guild_id)
    return {"webhooks": webhooks}


@app.post("/reddit/add")
def reddit_add(reddit_config: AddWebhook, background_tasks: BackgroundTasks):
    reddit_config.subreddit = reddit_config.target.lower()  # subreddit names are case-insensitive right?
    background_tasks.add_task(reddit_manager.add_scraper, config=reddit_config)
    return reddit_config


@app.post("/reddit/remove")
async def reddit_remove(reddit_config: RemoveWebhook):
    response = await reddit_manager.remove_scraper(scraper_id=reddit_config.id, guild_id=reddit_config.guild_id)

    if "error" not in response:
        response["ok"] = "ok"

    return response


@app.post("/reddit/clear")
async def reddit_clear(reddit_config: ClearPerGuild):
    removed = await reddit_manager.clear_scraper_per_guild(guild_id=reddit_config.guild_id)
    return {"ok": "ok", "removed": removed}


@app.get("/twitch/list/{guild_id}")
async def twitch_list(guild_id: int):
    webhooks = await twitch_manager.get_webhooks_per_guild(guild_id)
    return {"webhooks": webhooks}


@app.post("/twitch/add")
async def twitch_add(twitch_config: AddTwitchHook):
    twitch_config.streamer = twitch_config.target.lower()
    result = await twitch_manager.add_stream(config=twitch_config)
    return result


@app.post("/twitch/remove")
async def twitch_remove(twitch_config: RemoveWebhook):
    response = await twitch_manager.remove_stream(hook_id=twitch_config.id, guild_id=twitch_config.guild_id)

    if "error" not in response:
        response["ok"] = "ok"

    return response


@app.post("/reddit/clear")
async def twitch_clear(twitch_config: ClearPerGuild):
    removed = await twitch_manager.clear_per_guild(guild_id=twitch_config.guild_id)
    return {"ok": "ok", "removed": removed}


@app.post("/twitch/callback", response_class=PlainTextResponse)
async def twitch_subscription_verify(request: Request, background_tasks: BackgroundTasks):
    js = await request.json()
    print(js)

    if "challenge" in js:
        return js['challenge']

    elif "event" in js:
        background_tasks.add_task(twitch_manager.process_incoming_notification, js['event'])
        return "ok"


@app.post("/roll")
def roll_dice(dice_to_roll: Dice):
    dice_pattern = xdice.Pattern(dice_to_roll.dices)

    # Ensure the number of dice the user asked to roll is reasonable
    total_dice = 0

    # for dice in dice_pattern.dices:
    #    total_dice += dice.amount
    #    if dice.sides > 100000 or total_dice > 200:
    #        # If they're not rolling a reasonable amount of dice, abort the roll
    #        return {'error': f"Can't roll `{dice_to_roll.dices}`, too many dice"}

    roll = dice_pattern.roll()
    fmt = dice_pattern.format_string

    special_message = ""
    roll_information = []

    # Loop over each dice roll and add it to the intermediate text
    for score in roll.scores():

        score_string = ""

        if len(score.detail) > 1:
            score_string = f"{score_string}{' + '.join(map(str, score.detail))}"
        else:
            score_string = f"{score_string}{score.detail[0]}"

        if not score.dropped:
            pass
        elif len(score.dropped) > 1:
            score_string = f"{score_string} ~~+ {' + '.join(map(str, score.dropped))}~~"
        else:
            score_string = f"{score_string} ~~+ {score.dropped[0]}~~"

        # Add a special message if a user rolls a 20 or 1
        if "d20" in score.name:
            if 1 in score.detail:
                special_message = "Aww, you rolled a natural 1."
            elif 20 in score.detail:
                special_message = "Yay! You rolled a natural 20."

        score_string = f"[{score_string}]"
        roll_information.append(score_string)

    # Put spaces between the operators in the xdice template
    for i in ["+", "-", "/", "*"]:
        format_string = fmt.replace(i, f" {i} ")

    # Format the intermediate text using the previous template
    rolls = format_string.format(*roll_information)

    rolls = rolls if len(rolls) < 1800 else "*rolls omitted*"
    msg = f"`{dice_to_roll.dices}` = {rolls} = {roll}"

    if special_message:
        msg = f"{msg}\n{special_message}"

    return {"ok": "ok", "result": msg}
