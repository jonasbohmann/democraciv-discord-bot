import logging
import typing
import pydantic

from .db.db import Database
from .provider.reddit import RedditManager
from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import PlainTextResponse
from .provider.twitch import TwitchManager

logging.basicConfig(level=logging.INFO)

app = FastAPI()
db = Database(dsn="postgres://jonas:PASSWORD@localhost/api_test")
reddit_manger = RedditManager(db=db)
twitch_manager = TwitchManager()


class SubredditScraperConfig(pydantic.BaseModel):
    subreddit: str
    webhook_url: str


class TwitchConfig(pydantic.BaseModel):
    streamer: str
    webhook_url: str
    everyone_ping: bool


class RedditBulkSetup(pydantic.BaseModel):
    scraper: typing.Dict[str, typing.Set[str]]


class TwitchBulkSetup(pydantic.BaseModel):
    streams: typing.Dict[str, typing.Dict[str, typing.Union[str, bool]]]


@app.on_event("startup")
async def startup_event():
    pass


@app.get("/")
def read_root():
    return {"ok": "ok"}


@app.get("/reddit/status")
def reddit_status():
    return {"scrapers": reddit_manger.status}


@app.get("/twitch/status")
def twitch_status():
    return {"dict": twitch_manager._streams}


@app.post("/twitch/add")
async def twitch_sub(twitch_config: TwitchConfig):
    j = await twitch_manager.add_stream(twitch_config.streamer, twitch_config.webhook_url)
    return j


@app.post("/twitch/setup")
async def twitch_sub(bulk_setup: TwitchBulkSetup):
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


@app.post("/reddit/add")
def reddit_add(reddit_config: SubredditScraperConfig, background_tasks: BackgroundTasks):
    background_tasks.add_task(reddit_manger.start_scraper, subreddit=reddit_config.subreddit,
                              webhook_urls={reddit_config.webhook_url})
    return reddit_config


@app.post("/reddit/remove")
def reddit_remove(reddit_config: SubredditScraperConfig, background_tasks: BackgroundTasks):
    background_tasks.add_task(reddit_manger.remove_scraper, subreddit=reddit_config.subreddit,
                              webhook_urls=reddit_config.webhook_url)
    return reddit_config


@app.post("/reddit/setup")
def reddit_setup(bulk_setup: RedditBulkSetup, background_tasks: BackgroundTasks):
    background_tasks.add_task(reddit_manger.bulk_setup, bulk_setup.scraper)
    return {"ok": "ok"}
