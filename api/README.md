# api

FastAPI to receive incoming webhooks from Twitch and YouTube, poll subreddits for new posts, and to handle CPU or I/O intensive tasks that would 
block the bot's event loop if it did them itself. 
 

##  Requirements

*  [Python](https://www.python.org/downloads/) 3.7 or newer
*  [FastAPI](https://fastapi.tiangolo.com/) 0.62 or newer
*  [uvicorn](https://www.uvicorn.org/) 0.12.3 or newer
*  [PostgreSQL](https://www.postgresql.org/) 9.6 or newer 

Run `pip install -r requirements.txt` to install all required dependencies.

## Installation

After installing all the dependencies, create a `token.json` in the root /api folder.

The file should look like this:

```
{
  "db": {
    "dsn": ""
  },
  
  "twitch": {
    "client_id": "",
    "client_secret": "",
    "oauth_token": ""
  },

  "reddit": {
    "client_id": "",
    "client_secret": "",
    "refresh_token": "",
    "bearer_token": ""
  }
}
```

#### Docker

You can use the supplied Dockerfile to run the API as a Docker container.

The `docker-compose.yml` in the project root will start a bot container, an API container, and a PostgreSQL container.

####  Twitch 

Create an app [here](https://dev.twitch.tv/console/apps), copy its Client ID, Client Secret and [OAuth app access token]((https://dev.twitch.tv/docs/authentication/getting-tokens-oauth#oauth-client-credentials-flow)) 
and add it to `token.json`. 

App Access Tokens expire after around 58 days. If that happens, it will obtain a new one and replace the old one in `token.json`.

####  Reddit 

Create an app and put its Client ID, Client secret and a **refresh token** (not application token!) in `token.json`. 
Follow this [guide](https://github.com/reddit-archive/reddit/wiki/OAuth2) on how to get these. 
Make sure your refresh token has the `submit` and `edit` scopes. 


####  YouTube 

Follow [this](https://developers.google.com/youtube/v3) get an API key for the YouTube Data v3 API from Google.
