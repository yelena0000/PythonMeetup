from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from telegram.ext import Updater
from events_bot.models import Event, Participant
from events_bot.telegram_bot import send_new_event_notification

@receiver(post_save, sender=Event)
def notify_new_event(sender, instance, created, **kwargs):
    """Отправление уведомлений о новых событиях"""
    if created:
        try:
            updater = Updater(settings.TG_BOT_TOKEN, use_context=True)
            sent_count = send_new_event_notification(updater.bot, instance)
        except Exception as e:
            print(f"Не удалось выслать уведомление: {str(e)}")