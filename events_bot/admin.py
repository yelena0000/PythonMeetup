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
    list_display = ('name', 'telegram_username', 'is_speaker', 'is_event_manager')
    list_filter = ('is_speaker', 'is_event_manager')
    search_fields = ('name', 'telegram_username')


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('speaker', 'participant', 'timestamp', 'is_answered')
    list_filter = ('is_answered', 'speaker')
    search_fields = ('text', 'speaker__name', 'participant__name')


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
