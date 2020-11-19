import logging
import time

import pydantic
import xdice

from api.database import Database
from api.provider import RedditManager, TwitchManager
from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import PlainTextResponse

logging.basicConfig(level=logging.INFO)

app = FastAPI()
db = Database(dsn="postgres://postgres:PASSWORD@localhost/api_test")
reddit_manager = RedditManager(db=db)
twitch_manager = TwitchManager()


class AddSubredditScraper(pydantic.BaseModel):
    subreddit: str
    webhook_url: str
    webhook_id: int
    guild_id: int
    channel_id: int


class RemoveSubredditScraper(pydantic.BaseModel):
    id: int


class TwitchConfig(pydantic.BaseModel):
    streamer: str
    webhook_url: str
    everyone_ping: bool


class Dice(pydantic.BaseModel):
    dices: str


@app.on_event("startup")
async def startup_event():
    pass


@app.get("/")
def read_root():
    return {"ok": "ok"}


@app.post("/twitch/add")
async def twitch_sub(twitch_config: TwitchConfig):
    j = await twitch_manager.add_stream(twitch_config.streamer, twitch_config.webhook_url)
    return j


@app.get("/twitch/callback", response_class=PlainTextResponse)
async def twitch_subscription_verify(request: Request):
    if "hub.reason" in request.query_params:
        logging.error(f"could not subscribe to Twitch Webhook: {request.query_params['hub.reason']}")
    print(4)
    print(request)
    return request.query_params['hub.challenge']


@app.post("/twitch/callback")
async def twitch_webhook_received(request: Request, background_tasks: BackgroundTasks):
    background_tasks.add_task(twitch_manager.process_incoming_notification, request)
    print(5)
    print(await request.body())
    return {"ok": "thank you mr. twitch"}


@app.get("/reddit/list/{guild_id}")
async def reddit_list(guild_id: int):
    webhooks = await reddit_manager.get_webhooks_per_guild(guild_id)
    return {'webhooks': webhooks}


@app.post("/reddit/add")
def reddit_add(reddit_config: AddSubredditScraper, background_tasks: BackgroundTasks):
    reddit_config.subreddit = reddit_config.subreddit.lower()  # subreddit names are case-insensitive right?
    background_tasks.add_task(reddit_manager.add_scraper, config=reddit_config)
    return reddit_config


@app.post("/reddit/remove")
async def reddit_remove(reddit_config: RemoveSubredditScraper):
    response = await reddit_manager.remove_scraper(config=reddit_config)
    response["ok"] = "ok"
    return response


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

    msg = f"`{dice_to_roll.dices}` = {rolls} = {roll}"

    if special_message:
        msg = f"{msg}\n{special_message}"

    return {'ok': 'ok', 'result': msg}
