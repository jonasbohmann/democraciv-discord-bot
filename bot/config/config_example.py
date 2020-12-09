# Rename this to config.py

# Democraciv Discord Bot

API_URL = "http://localhost:8000"
DEMOCRACIV_GUILD_ID = 208984105310879744  # dciv

BOT_PREFIX = "m-"
BOT_ADDITIONAL_PREFIXES = [BOT_PREFIX, "maori- ", "maori-", "maori ", "maori", "mao- ", "mao-", "mao ", "mao"]

BOT_COMMAND_COOLDOWN = 1.5  # in seconds
BOT_VERSION = "2.0.0-beta"
BOT_EMBED_COLOUR = 0x1B1C20
BOT_TECHNICAL_NOTIFICATIONS_CHANNEL = 661201604493443092

# Starboard
STARBOARD_ENABLED = True
STARBOARD_STAR_EMOJI = "\U00002b50"
STARBOARD_CHANNEL = 680565146133069873  # The Discord channel for the starboard
STARBOARD_MIN_STARS = 5  # How many star reactions does a message need to be added to the starboard
STARBOARD_MAX_AGE = 7  # Messages older than X days won't be allowed into the starboard
STARBOARD_REDDIT_SUMMARY_ENABLED = True
STARBOARD_REDDIT_SUBREDDIT = "democraciv"
STARBOARD_REDDIT_USERNAME = "DerJonasBot"

# Custom Emojis
YES = "<:green:783014904613437501>"
NO = "<:red:783014904634015805>"
USER_INTERACTION_REQUIRED = "<:speech:783734469584093185>"
HINT = "<:info:781283291176108042>"
JOIN = "<:join:783058716336980008>"
LEAVE = "<:leave:783058716244049931>"

LEG_SUBMIT_MOTION = "<:motion:683370053508399121>"
LEG_SUBMIT_BILL = "<:bill:683370062358642737>"
LEG_BILL_STATUS_GREEN = "<:green:660562089298886656>"
LEG_BILL_STATUS_YELLOW = "<:yellow:660562049817903116>"
LEG_BILL_STATUS_RED = "<:red:660562078217797647>"
LEG_BILL_STATUS_GRAY = "<:gray:660562063122497569>"

WIKIPEDIA_LOGO = "<:wikipedia:660487143856275497>"

GUILD_SETTINGS_ENABLED = "<:enabled:683808377989890049>"
GUILD_SETTINGS_DISABLED = "<:disabled:683808378132365315>"
GUILD_SETTINGS_GRAY_ENABLED = "<:gray_yes:683808378329628680>"
GUILD_SETTINGS_GRAY_DISABLED = "<:gray_x:683808378501333058>"
GUILD_SETTINGS_GEAR = "<:settings:699978748904079431>"

HELP_FIRST = "<:first:685985692953870413>"
HELP_PREVIOUS = "<:left:685985693285220392>"
HELP_NEXT = "<:right:685985692857401353>"
HELP_LAST = "<:last:685985693264379904>"
HELP_BOT_HELP = "<:qe:685986162225184788>"

# Database
DATABASE_DAILY_BACKUP_ENABLED = True
DATABASE_DAILY_BACKUP_DISCORD_CHANNEL = 738903909535318086
DATABASE_DAILY_BACKUP_INTERVAL = 72  # hours

# Google Cloud Platform
GOOGLE_CLOUD_PLATFORM_CLIENT_SECRETS_FILE = "bot/config/google_client_secret.json"
GOOGLE_CLOUD_PLATFORM_OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/forms",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/script.external_request",
    "https://www.googleapis.com/auth/drive"
]
