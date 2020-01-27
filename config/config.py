# Configuration for the Democraciv Bot


# Bot Configuration
BOT_NAME = 'Democraciv Bot'
BOT_PREFIX = '-'
BOT_COMMAND_COOLDOWN = 2.0  # seconds
BOT_DESCRIPTION = 'Discord Bot for the r/Democraciv community.'
BOT_VERSION = '0.16.1'
BOT_ICON_URL = 'https://cdn.discordapp.com/attachments/585502938571604056/586310405618532362/final_pride2.png'
BOT_AUTHOR = 'DerJonas#8109'
BOT_AUTHOR_ID = 212972352890339328
DEMOCRACIV_SERVER_ID = 208984105310879744  # Democraciv
# DEMOCRACIV_SERVER_ID = 653946455337467904  # Democraciv Bot Support
# DEMOCRACIV_SERVER_ID = 232108753477042187  # Test Server


# Database Configuration
DATABASE_DAILY_BACKUP_ENABLED = True
DATABASE_DAILY_BACKUP_DISCORD_CHANNEL = 656214962854821928


# Reddit Notifications
REDDIT_ENABLED = True
REDDIT_SUBREDDIT = 'democraciv'
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
