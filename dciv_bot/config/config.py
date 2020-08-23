# Configuration for the Democraciv Bot


# Bot Configuration
BOT_NAME = 'Democraciv Bot'
BOT_PREFIX = '-'
BOT_COMMAND_COOLDOWN = 2.0  # In seconds
BOT_DESCRIPTION = 'Discord Bot for the r/Democraciv community.'
BOT_VERSION = '1.3.0'
BOT_ICON_URL = 'https://cdn.discordapp.com/attachments/585502938571604056/586310405618532362/final_pride2.png'
BOT_EMBED_COLOUR = 0x1b1c20  # in hex as int
DEMOCRACIV_GUILD_ID = 208984105310879744  # Democraciv
# DEMOCRACIV_GUILD_ID = 653946455337467904  # Democraciv Bot Support
# DEMOCRACIV_GUILD_ID = 232108753477042187  # Test Server

# Starboard Configuration
STARBOARD_ENABLED = True
STARBOARD_CHANNEL = 680565146133069873  # The Discord channel for the starboard
STARBOARD_REDDIT_SUMMARY_ENABLED = True  # Toggle weekly posts to r/REDDIT_SUBREDDIT with last week's starboard
STARBOARD_MIN_STARS = 5  # How many star reactions does a message need to be added to the starboard
STARBOARD_MAX_AGE = 7  # Messages older than 7 days won't be allowed into the starboard
STARBOARD_STAR_EMOJI = "\U00002b50"

# Custom Emoji Configuration
LEG_SUBMIT_MOTION = "<:motion:683370053508399121>"
LEG_SUBMIT_BILL = "<:bill:683370062358642737>"
LEG_BILL_STATUS_GREEN = "<:green:660562089298886656>"
LEG_BILL_STATUS_YELLOW = "<:yellow:660562049817903116>"
LEG_BILL_STATUS_RED = "<:red:660562078217797647>"
LEG_BILL_STATUS_GRAY = "<:gray:660562063122497569>"
NATION_FLAG = "<:arabia:721366589861265429>"
REDDIT_LOGO = "<:reddit:660114002533285888>"
YOUTUBE_LOGO_UPLOAD = "<:youtubeiconwhite:660114810444447774>"
YOUTUBE_LOGO_STREAM = "<:youtubeiconred:660897027114401792>"
TWITCH_LOGO = "<:twitch:660116652012077080>"
WIKIPEDIA_LOGO = "<:wikipedia:660487143856275497>"
FANDOM_WIKI_LOGO = "<:fandom:660488383855984640>"
SPOTIFY_LOGO = "<:spotify:665703093425537046>"
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

# Database Configuration
DATABASE_DAILY_BACKUP_ENABLED = True
DATABASE_DAILY_BACKUP_DISCORD_CHANNEL = 738903909535318086
DATABASE_DAILY_BACKUP_INTERVAL = 72  # hours
DATABASE_DAILY_BACKUP_BANK_OF_DEMOCRACIV_BACKUP = True
DATABASE_DAILY_BACKUP_BANK_OF_DEMOCRACIV_DATABASE = "live_bank"

# Reddit Notifications
REDDIT_ENABLED = True
REDDIT_SUBREDDIT = 'democraciv'  # This will also be used for Starboard subreddit
REDDIT_ANNOUNCEMENT_CHANNEL = 330162836095631360  # The Discord Channel in which the bot will post Reddit notifications

# Twitch Notifications
TWITCH_ENABLED = True
TWITCH_CHANNEL = 'democraciv'  # The twitch.tv streamer that the bot should check for live streams
TWITCH_ANNOUNCEMENT_CHANNEL = 209432307730350080  # The Discord Channel in which the bot will post Twitch notifications
TWITCH_EVERYONE_PING_ON_ANNOUNCEMENT = True
TWITCH_ANNOUNCEMENT_TO_REDDIT = True  # Announces live streams on r/REDDIT_SUBREDDIT as well. Reddit client id,
                                      # client secret and refresh token need to be provided in token.py for this to work


# YouTube Notifications
YOUTUBE_ENABLED = True
YOUTUBE_VIDEO_UPLOADS_ENABLED = True
YOUTUBE_VIDEO_UPLOADS_TO_REDDIT = True  # Announces new YouTube uploads on r/REDDIT_SUBREDDIT. Reddit client id, client
                                        # secret and refresh token need to be provided in token.py for this to work
YOUTUBE_LIVESTREAM_ENABLED = False
YOUTUBE_EVERYONE_PING_ON_STREAM = False
YOUTUBE_CHANNEL_ID = 'UC-NukxPakwQIvx73VjtIPnw'  # The channel ID of the YouTuber's channel
YOUTUBE_CHANNEL_UPLOADS_PLAYLIST = 'UU-NukxPakwQIvx73VjtIPnw'  # The playlist ID of the YouTuber's 'Uploads' playlist
YOUTUBE_ANNOUNCEMENT_CHANNEL = 209432307730350080  # The Discord Channel for YouTube notifications

# Google Cloud Platform Configuration
GOOGLE_CLOUD_PLATFORM_CLIENT_SECRETS_FILE = "dciv_bot/config/google_cloud_platform_client_secret.json"
GOOGLE_CLOUD_PLATFORM_CLIENT_OAUTH_CREDENTIALS_FILE = "dciv_bot/config/google_cloud_platform_oauth2_credentials.json"
GOOGLE_CLOUD_PLATFORM_OAUTH_SCOPES = ['https://www.googleapis.com/auth/forms',
                                      'https://www.googleapis.com/auth/documents']
