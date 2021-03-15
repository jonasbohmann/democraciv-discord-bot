import asyncio
import json
import logging
import pathlib
import sys
import asyncpg
import pydantic
import uvicorn
import xdice

from ml import information_extraction

try:
    import uvloop

    uvloop.install()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [API] %(message)s", datefmt="%d.%m.%Y %H:%M:%S")
sys.path.append(str(pathlib.Path(__file__).parent.parent))

from api.provider import RedditManager, TwitchManager
from api.ml import question_answering
from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import PlainTextResponse
from fastapi.logger import logger

TOKEN_PATH = f"{pathlib.Path(__file__).parent}/token.json"


class Database:
    def __init__(self):
        self.get_dsn()
        self._loop = asyncio.get_event_loop()
        self.pool = None
        self.ready = asyncio.Event()
        self._loop.create_task(self.make_pool())
        self._lock = asyncio.Lock()

    def get_dsn(self):
        with open(TOKEN_PATH, "r") as token_file:
            token_json = json.load(token_file)
            self.dsn = token_json["db"]["dsn"]

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
                    
                    CREATE TABLE IF NOT EXISTS twitch_eventsub_subscription(
                    id serial PRIMARY KEY,
                    twitch_subscription_id text UNIQUE NOT NULL,
                    streamer text NOT NULL,
                    streamer_id text NOT NULL
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

    async def make_pool(self, retry=False):
        # todo - why does this throw ConnectionRefusedError on the first try with docker-compose

        async with self._lock:
            try:
                self.pool = await asyncpg.create_pool(self.dsn)
            except ConnectionRefusedError:
                if not retry:
                    await asyncio.sleep(3)
                    await self.make_pool(retry=True)
                    return
                raise

            await self.apply_schema()
            self.ready.set()
            return self.pool


app = FastAPI()
db = Database()
bert_qa = question_answering.BERTQuestionAnswering(db=db,
                                                   index_directory=str(pathlib.Path(__file__).parent) + "/ml/index")
holmes_ie = information_extraction.InformationExtraction(db=db)
reddit_manager = RedditManager(db=db, token_path=TOKEN_PATH)
twitch_manager = TwitchManager(db=db, token_path=TOKEN_PATH)


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


class SubmitRedditPost(pydantic.BaseModel):
    subreddit: str
    title: str
    content: str


class DeleteRedditPost(pydantic.BaseModel):
    id: str


class Bill(pydantic.BaseModel):
    id: int


@app.on_event("startup")
async def startup_event():
    await db.make_pool()
    await bert_qa.make()
    await holmes_ie.register_documents()
    logger.info("API ready to serve")


@app.get("/")
async def ok():
    return {"ok": "ok"}


@app.get("/reddit/list/{guild_id}")
async def reddit_list(guild_id: int):
    webhooks = await reddit_manager.get_webhooks_per_guild(guild_id)
    return {"webhooks": webhooks}


@app.post("/reddit/add")
async def reddit_add(reddit_config: AddWebhook):
    reddit_config.target = reddit_config.target.lower()  # subreddit names are case-insensitive right?
    await reddit_manager.add_webhook(config=reddit_config)
    return reddit_config


@app.post("/reddit/remove")
async def reddit_remove(reddit_config: RemoveWebhook):
    response = await reddit_manager.remove_webhook(hook_id=reddit_config.id, guild_id=reddit_config.guild_id)

    if "error" not in response:
        response["ok"] = "ok"

    return response


@app.post("/reddit/post")
async def reddit_post(submission: SubmitRedditPost):
    return await reddit_manager.post_to_reddit(
        subreddit=submission.subreddit, title=submission.title, content=submission.content
    )


@app.post("/reddit/post/delete")
async def reddit_post_delete(post: DeleteRedditPost):
    return await reddit_manager.delete_reddit_post(post_id=post.id)


@app.post("/reddit/clear")
async def reddit_clear(reddit_config: ClearPerGuild):
    removed = await reddit_manager.clear_per_guild(guild_id=reddit_config.guild_id)
    return {"ok": "ok", "removed": removed}


@app.get("/twitch/list/{guild_id}")
async def twitch_list(guild_id: int):
    webhooks = await twitch_manager.get_webhooks_per_guild(guild_id)
    return {"webhooks": webhooks}


@app.post("/twitch/add")
async def twitch_add(twitch_config: AddTwitchHook):
    twitch_config.target = twitch_config.target.lower()
    result = await twitch_manager.add_webhook(config=twitch_config)
    return result


@app.post("/twitch/remove")
async def twitch_remove(twitch_config: RemoveWebhook):
    response = await twitch_manager.remove_webhook(hook_id=twitch_config.id, guild_id=twitch_config.guild_id)

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
        background_tasks.add_task(
            twitch_manager.add_twitch_subscription_id,
            js["subscription"]["condition"]["broadcaster_user_id"],
            js["subscription"]["id"],
        )
        return js["challenge"]

    elif "event" in js:
        background_tasks.add_task(twitch_manager.process_incoming_notification, js["event"])
        return "ok"


def _roll_dice(dice_to_roll: str):
    dice_pattern = xdice.Pattern(dice_to_roll)

    # Ensure the number of dice the user asked to roll is reasonable
    # total_dice = 0

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
    rolls, _, _ = rolls.partition("#")

    rolls = rolls if len(rolls) < 1800 else "*rolls omitted*"

    pretty_dice_to_roll, _, comment = dice_to_roll.partition("#")

    if comment:
        msg = f"`{pretty_dice_to_roll.strip()}` {comment.strip()} = {rolls} = {roll}"
    else:
        msg = f"`{dice_to_roll}` = {rolls} = {roll}"

    if special_message:
        msg = f"{msg}\n{special_message}"

    return msg


@app.post("/roll")
def roll_dice(dice_to_roll: Dice):
    try:
        return {"ok": "ok", "result": _roll_dice(dice_to_roll.dices)}
    except (SyntaxError, TypeError, ValueError, IndexError):
        return {"error": "invalid dice syntax"}


class Question(pydantic.BaseModel):
    question: str


@app.post("/ml/question_answering")
def okay(question: Question):
    try:
        answers = bert_qa.qa.ask(question.question, n_answers=5, n_docs_considered=10, batch_size=1)
        result = []

        for answer in answers:
            result.append(
                {"answer": answer['answer'], "score": float(answer['confidence']), "context": answer['context']})

        return result
    except Exception as e:
        # todo too broad
        logger.error(f"error in /ml/question_answering: {type(e)}: {e}")
        return {"error": "who knows"}


@app.post("/ml/information_extraction")
def okay(question: Question):
    answers = holmes_ie.search(question.question)
    return answers


@app.post("/bill/add")
async def new_bill(bill: Bill):
    await bert_qa.add_bill(bill.id)
    await holmes_ie.add_bill(bill.id)


@app.post("/bill/update")
async def update_bill(bill: Bill):
    await holmes_ie.add_bill(bill.id)

    # documents in our index are not unique so we cannot reasonably delete just the one bill
    await bert_qa.index()


@app.post("/bill/delete")
async def delete_bill(bill: Bill):
    await holmes_ie.delete_bill(bill.id)

    # documents in our index are not unique so we cannot reasonably delete just the one bill
    await bert_qa.index()


if __name__ == "__main__":
    logger.info("Starting app...")
    uvicorn.run(app, host="0.0.0.0", port="8000")
