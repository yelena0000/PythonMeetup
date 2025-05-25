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


class TimeSlotInline(admin.TabularInline):
    model = TimeSlot
    extra = 1
    fields = ('speaker', 'title', 'start_time', 'end_time', 'description')
    ordering = ('start_time',)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'date', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('title', 'description')
    inlines = [SpeakerInline, TimeSlotInline]


@admin.register(Speaker)
class SpeakerAdmin(admin.ModelAdmin):
    list_display = ('name', 'telegram_username')
    search_fields = ('name', 'telegram_username')


@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ('name', 'telegram_username', 'is_speaker', 'is_event_manager', 'is_subscribed')
    list_filter = ('is_speaker', 'is_event_manager', 'is_subscribed')
    search_fields = ('name', 'telegram_username')


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('speaker', 'participant', 'short_text', 'timestamp', 'is_answered')
    list_filter = ('is_answered', 'speaker', 'event')
    search_fields = ('text', 'speaker__name', 'participant__name')
    list_editable = ('is_answered',)  # Позволяет отмечать "ответил" прямо в списке
    readonly_fields = ('timestamp',)
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
    list_display = ('participant', 'amount', 'timestamp')
    list_filter = ('event',)
    search_fields = ('participant__name',)


@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display = ('event', 'speaker', 'start_time', 'end_time', 'title')
    list_filter = ('event', 'speaker')
    search_fields = ('title', 'speaker__name')
