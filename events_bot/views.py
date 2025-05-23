from django.conf import settings
from django.utils import timezone
from django.db import transaction, models
from .models import Event, Speaker, TimeSlot, Participant, Question
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from environs import Env
from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned

env = Env()
env.read_env()
BOT_TOKEN = settings.TG_BOT_TOKEN


def get_program():
    today = timezone.now().date()
    today_events = Event.objects.filter(date=today).prefetch_related(
        'speakers', 'time_slots').order_by('time_slots__start_time')
    program = []
    for event in today_events:
        for timeslot in event.time_slots.all():
            speaker = timeslot.speaker.name
            program.append(
                f"{timeslot.start_time.strftime('%H:%M')} - {timeslot.end_time.strftime('%H:%M')}: "
                f"{timeslot.title} ({', '.join(speaker)})"
            )
    return program


def serialize_current_events():
    now = timezone.now()
    current_timeslots = TimeSlot.objects.filter(
        start_time__lte=now, end_time__gte=now, event__is_active=True,
    ).prefetch_related('event__speakers', 'speaker').order_by('start_time')
    events_info = []
    speakers_list = []
    for timeslot in current_timeslots:
        speaker = timeslot.speaker
        speakers_list.append(speaker)
        events_info.append(
            f"{timeslot.start_time.strftime('%H:%M')} - {timeslot.end_time.strftime('%H:%M')}: "
            f"{speaker.name} - {timeslot.event.title}"
        )
    return {
        'events': events_info,
        'speakers': speakers_list,
    }


def get_staff_ids():
    participants = Participant.objects.all()
    managers = participants.filter(is_event_manager=True)
    managers_ids = [str(manager.telegram_id) for manager in managers]
    speakers = participants.filter(is_speaker=True)
    speakers_ids = [str(speaker.telegram_id) for speaker in speakers]
    return {'managers_ids': managers_ids, 'speakers_ids': speakers_ids}


def get_chat_id_by_username(username):
    try:
        participant = Participant.objects.get(
            is_speaker=True,
            telegram_username=username
        )
        return participant.telegram_id
    except ObjectDoesNotExist:
        raise Exception(f"Спикер {username} не найден")
    except MultipleObjectsReturned:
        raise Exception(f"Найдено несколько спикеров @{username}")


def send_question(speaker_username, participant_id, participant_name, text):
    bot = Bot(token=BOT_TOKEN)

    try:
        with transaction.atomic():
            # Ищем спикера ТОЛЬКО по telegram_username
            speaker = Speaker.objects.get(telegram_username=speaker_username)

            # Проверяем, что спикер привязан к активному мероприятию
            if not speaker.events.filter(is_active=True).exists():
                raise Exception("Спикер не привязан к активному мероприятию")

            participant, _ = Participant.objects.get_or_create(
                telegram_id=participant_id,
                defaults={'name': participant_name}
            )
            event = speaker.events.filter(is_active=True).first()

            # Создаем вопрос в БД
            question = Question.objects.create(
                event=event,
                speaker=speaker,
                participant=participant,
                text=text
            )

            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Ответить", callback_data=f'answer_{question.id}')]
            ])

            bot.send_message(
                chat_id=speaker.telegram_id,
                text=f"❓ Новый вопрос от {participant_name}:\n\n{text}",
                reply_markup=reply_markup
            )

            return True

    except Speaker.DoesNotExist:
        raise Exception(f"Спикер @{speaker_username} не найден")
    except Exception as e:
        raise Exception(f"Ошибка при отправке вопроса: {str(e)}")
