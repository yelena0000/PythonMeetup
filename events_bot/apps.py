from django.apps import AppConfig

class EventsBotConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'events_bot'

    def ready(self):
        import events_bot.signals
