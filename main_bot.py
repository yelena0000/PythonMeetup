import os
import django
from telegram.ext import Updater

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'meetup.settings')
django.setup()

from events_bot.telegram_bot import start_bot


if __name__ == '__main__':
    start_bot()
