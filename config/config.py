# Configuration for the Democraciv Bot


# Bot Configuration
BOT_NAME = 'Democraciv Bot'
BOT_PREFIX = '-'
BOT_COMMAND_COOLDOWN = 2.0  # In seconds
BOT_DESCRIPTION = 'Discord Bot for the r/Democraciv community.'
BOT_VERSION = '0.16.2'
BOT_ICON_URL = 'https://cdn.discordapp.com/attachments/585502938571604056/586310405618532362/final_pride2.png'
DEMOCRACIV_GUILD_ID = 208984105310879744  # Democraciv
# DEMOCRACIV_GUILD_ID = 653946455337467904  # Democraciv Bot Support
# DEMOCRACIV_GUILD_ID = 232108753477042187  # Test Server

# Starboard Configuration
STARBOARD_ENABLED = True
STARBOARD_CHANNEL = 639549494693724170  # The Discord channel for the starboard
STARBOARD_REDDIT_SUMMARY_ENABLED = True  # Toggle weekly posts to r/REDDIT_SUBREDDIT with last week's starboard
STARBOARD_MIN_STARS = 4  # How many star reactions does a message need to be added to the starboard
STARBOARD_MAX_AGE = 7  # Messages older than 7 days won't be allowed into the starboard
STARBOARD_STAR_EMOJI = "\U00002b50"

# Database Configuration
DATABASE_DAILY_BACKUP_ENABLED = True
DATABASE_DAILY_BACKUP_DISCORD_CHANNEL = 656214962854821928

# Reddit Notifications
REDDIT_ENABLED = True
REDDIT_SUBREDDIT = 'democraciv'  # This will also be used for Starboard subreddit
REDDIT_ANNOUNCEMENT_CHANNEL = 330162836095631360  # The Discord Channel in which the bot will post Reddit notifications

# Twitch Notifications
TWITCH_ENABLED = True
TWITCH_CHANNEL = 'democraciv'  # The twitch.tv streamer that the bot should check for live streams
TWITCH_ANNOUNCEMENT_CHANNEL = 209432307730350080  # The Discord Channel in which the bot will post Twitch notifications
TWITCH_EVERYONE_PING_ON_ANNOUNCEMENT = True

# YouTube Notifications
YOUTUBE_ENABLED = True
YOUTUBE_VIDEO_UPLOADS_ENABLED = True
YOUTUBE_LIVESTREAM_ENABLED = False
YOUTUBE_EVERYONE_PING_ON_STREAM = False
YOUTUBE_CHANNEL_ID = 'UC-NukxPakwQIvx73VjtIPnw'  # The channel ID of the YouTuber's channel
YOUTUBE_CHANNEL_UPLOADS_PLAYLIST = 'UU-NukxPakwQIvx73VjtIPnw'  # The playlist ID of the YouTuber's 'Uploads' playlist
YOUTUBE_ANNOUNCEMENT_CHANNEL = 209432307730350080  # The Discord Channel for YouTube notifications
