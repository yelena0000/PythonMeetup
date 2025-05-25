from django.contrib import admin
from .models import (
    TimeSlot,
    Event,
    Speaker,
    Participant,
    Question,
    Donation,
    ConnectionRequest
)


class SpeakerInline(admin.TabularInline):
    model = Speaker.events.through
    extra = 1
    verbose_name = "Спикер"
    verbose_name_plural = "Спикеры мероприятия"


class TimeSlotInline(admin.TabularInline):
    model = TimeSlot
    extra = 1
    fields = ('speaker', 'title', 'start_time', 'end_time', 'description')
    ordering = ('start_time',)
    verbose_name = "Временной слот"
    verbose_name_plural = "Расписание выступлений"


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'date', 'is_active', 'speakers_list')
    list_filter = ('is_active', 'date')
    search_fields = ('title', 'description')
    inlines = [SpeakerInline, TimeSlotInline]
    date_hierarchy = 'date'
    list_per_page = 20

    def speakers_list(self, obj):
        return ", ".join([speaker.name for speaker in obj.speakers.all()])
    speakers_list.short_description = 'Спикеры'


@admin.register(Speaker)
class SpeakerAdmin(admin.ModelAdmin):
    list_display = ('name', 'telegram_username', 'telegram_id', 'events_count')
    search_fields = ('name', 'telegram_username', 'telegram_id')
    list_per_page = 20
    filter_horizontal = ('events',)

    def events_count(self, obj):
        return obj.events.count()
    events_count.short_description = 'Мероприятий'


@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ('name', 'telegram_username', 'is_speaker', 'is_event_manager', 'is_subscribed', 'has_profile')
    list_filter = ('is_speaker', 'is_event_manager', 'is_subscribed')
    search_fields = ('name', 'telegram_username', 'telegram_id')
    list_per_page = 20
    filter_horizontal = ('registered_events',)

    def has_profile(self, obj):
        return obj.has_profile
    has_profile.boolean = True
    has_profile.short_description = 'Анкета заполнена'


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('short_text', 'speaker', 'participant', 'timestamp', 'is_answered', 'event')
    list_filter = ('is_answered', 'speaker', 'event')
    search_fields = ('text', 'speaker__name', 'participant__name')
    list_editable = ('is_answered',)
    readonly_fields = ('timestamp',)
    list_per_page = 20
    date_hierarchy = 'timestamp'

    fieldsets = (
        (None, {
            'fields': ('event', 'speaker', 'participant', 'text', 'is_answered')
        }),
        ('Метаданные', {
            'fields': ('timestamp',),
            'classes': ('collapse',)
        }),
    )

    def short_text(self, obj):
        return f"{obj.text[:50]}..." if len(obj.text) > 50 else obj.text
    short_text.short_description = 'Текст вопроса'


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    list_display = ('participant', 'amount', 'timestamp', 'is_confirmed', 'event')
    list_filter = ('event', 'is_confirmed')
    search_fields = ('participant__name', 'payment_id')
    list_per_page = 20
    date_hierarchy = 'timestamp'


@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display = ('event', 'speaker', 'start_time', 'end_time', 'title', 'is_extended')
    list_filter = ('event', 'speaker')
    search_fields = ('title', 'speaker__name')
    list_per_page = 20
    date_hierarchy = 'start_time'
    list_editable = ('is_extended',)
