from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    Filters,
    ConversationHandler
)
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    BotCommand,
    Update,
    ReplyKeyboardRemove
)
from django.conf import settings
from yookassa import Payment, Configuration
import uuid
from django.utils import timezone

from events_bot.models import Event, Participant, Donation, Question, Speaker
from events_bot.views import send_question

(
    CHOOSE_CUSTOM_AMOUNT,
    SELECTING_SPEAKER,
    AWAITING_QUESTION,
    CONFIRMING_QUESTION,
    SELECTING_EVENT,
    CONFIRMING_REGISTRATION,
    SUBSCRIBING,
    MAILING,
    CONFIRMING_MAILING,
    UNSUBSCRIBING,
    SELECTING_EVENT_PARTICIPANT,
    CONFIRMING_PARTICIPANT_REGISTRATION,
    SHOW_MY_EVENTS,
    CONFIRMING_UNREGISTER,
    AWAITING_NAME,
    AWAITING_BIO,
    VIEWING_PROFILE
) = range(17)

# Инициализация ЮKassa
Configuration.account_id = settings.YOOKASSA_SHOP_ID
Configuration.secret_key = settings.YOOKASSA_SECRET_KEY


def get_main_keyboard(participant):
    """Кнопки главного меню"""
    keyboard = [
        ["📅 Мероприятие", "📝 Регистрация"],
        ["🙋 Пообщаться", "🎁 Поддержать"]
    ]

    # Добавляем кнопку "Мои вопросы" только для спикеров
    if participant.is_speaker:
        keyboard.append(["❓ Мои вопросы"])

    # Добавляем кнопку "Сделать рассылку" только для организаторов и спикеров
    if participant.is_event_manager:
        keyboard.append(["📢 Сделать рассылку"])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)


def event_menu(update, context):
    """Обработчик меню 'Мероприятие'"""
    user = update.message.from_user
    participant, _ = Participant.objects.get_or_create(
        telegram_id=user.id,
        defaults={
            'telegram_username': user.username,
            'name': user.first_name or 'Аноним'
        }
    )

    keyboard = [
        ["📜 Программа", "📋 Мои мероприятия"],
        ["❓ Задать вопрос спикеру"],
        ["🎤 Кто выступает сейчас?"],
    ]

    # Кнопка подписки/отписки
    if not participant.is_subscribed:
        keyboard.append(["🔙 Назад", "✅ Подписаться на рассылку"])
    else:
        keyboard.append(["🔙 Назад", "❌ Отписаться от рассылки"])

    update.message.reply_text(
        "Выберите действие:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )


def registration_menu(update, context):
    """Обработчик меню 'Регистрация'"""
    keyboard = [
        ["👤 Зарегистрироваться участником"],
        ["🎤 Зарегистрироваться спикером"],
        ["🔙 Назад"]
    ]

    update.message.reply_text(
        "Выберите тип регистрации:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )


def start(update, context):
    user = update.message.from_user
    participant, _ = Participant.objects.get_or_create(
        telegram_id=user.id,
        defaults={
            'telegram_username': user.username,
            'name': user.first_name or 'Аноним'
        }
    )

    event = Event.objects.filter(is_active=True).first()
    event_name = event.title if event else "Python Meetup"

    main_menu_keyboard = get_main_keyboard(participant)

    update.message.reply_text(
        f"✨ <b>Привет, {user.first_name}!</b> ✨\n\n"
        f"Я бот для <i>{event_name}</i>\n\n"
        "Что я умею:\n"
        "• <b>📅 Мероприятие</b> - программа, вопросы, спикеры, предстоящие события\n"
        "• <b>📝 Регистрация</b> - зарегистрироваться как участник или спикер\n"
        "• <b>🙋 Пообщаться</b> - знакомства с участниками\n"
        "• <b>🎁 Поддержать</b> - сделать донат на развитие\n\n"
        "Используйте кнопки ниже для навигации:",
        reply_markup=main_menu_keyboard,
        parse_mode='HTML'
    )


def program(update, context):
    event = Event.objects.filter(is_active=True).first()
    if event:
        program_text = event.get_program()
        update.message.reply_text(
            f"📜 <b>Программа мероприятия:</b>\n\n"
            f"{program_text}\n\n"
            f"<i>Ждем вас {event.date.strftime('%d.%m.%Y')}!</i>",
            parse_mode='HTML'
        )
    else:
        update.message.reply_text(
            "📭 Сейчас нет активных мероприятий\n"
            "Следите за анонсами!",
            parse_mode='HTML'
        )


def donate(update, context):
    if not Event.objects.filter(is_active=True).exists():
        update.message.reply_text(
            "🙅‍♂️ <b>Сейчас нет активных мероприятий</b>\n"
            "Донаты временно недоступны",
            parse_mode='HTML'
        )
        return

    keyboard = [
        [InlineKeyboardButton("💵 100 ₽", callback_data='donate_100')],
        [InlineKeyboardButton("💵 300 ₽", callback_data='donate_300')],
        [InlineKeyboardButton("💵 500 ₽", callback_data='donate_500')],
        [InlineKeyboardButton(
            "✨ Другая сумма", callback_data='donate_custom')],
    ]
    update.message.reply_text(
        "🎁 <b>Выберите сумму доната:</b>\n"
        "Ваша поддержка помогает развивать комьюнити!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )


def handle_fixed_donate_callback(update, context):
    query = update.callback_query
    query.answer()

    if not Event.objects.filter(is_active=True).exists():
        query.edit_message_text(
            "🙅‍♂️ Сейчас нет активных мероприятий для доната")
        return ConversationHandler.END

    try:
        amount = int(query.data.split('_')[1])
        create_payment(update, context, amount)
    except (IndexError, ValueError):
        query.edit_message_text("❌ Ошибка при обработке суммы.")
    return ConversationHandler.END


def handle_custom_donate_callback(update, context):
    query = update.callback_query
    query.answer()

    if not Event.objects.filter(is_active=True).exists():
        query.edit_message_text(
            "🙅‍♂️ Сейчас нет активных мероприятий для доната")
        return ConversationHandler.END

    query.edit_message_text(
        "💫 <b>Введите сумму доната в рублях</b>\n"
        "(от 10 до 15000):",
        parse_mode='HTML'
    )
    return CHOOSE_CUSTOM_AMOUNT


def handle_custom_amount(update, context):
    try:
        amount = int(update.message.text.strip())
        if amount < 10 or amount > 15000:
            update.message.reply_text(
                "⚠️ <b>Сумма должна быть от 10 до 15000 ₽</b>\n"
                "Пожалуйста, введите корректную сумму:",
                parse_mode='HTML'
            )
            return CHOOSE_CUSTOM_AMOUNT

        create_payment(update, context, amount)
        return ConversationHandler.END

    except ValueError:
        update.message.reply_text(
            "🔢 <b>Пожалуйста, введите число</b>\n"
            "Например: 250 или 1000",
            parse_mode='HTML'
        )
        return CHOOSE_CUSTOM_AMOUNT


def cancel(update, context):
    update.message.reply_text(
        "❌ <b>Донат отменён</b>\n"
        "Вы можете вернуться к этому позже",
        parse_mode='HTML'
    )
    return ConversationHandler.END


def create_payment(update, context, amount):
    if update.callback_query:
        user = update.callback_query.from_user
        chat_id = update.callback_query.message.chat_id
    else:
        user = update.message.from_user
        chat_id = update.message.chat_id

    event = Event.objects.filter(is_active=True).first()
    if not event:
        error_msg = "🙅‍♂️ Сейчас нет активных мероприятий для доната"
        if update.callback_query:
            update.callback_query.edit_message_text(error_msg)
        else:
            update.message.reply_text(error_msg)
        return

    participant, _ = Participant.objects.get_or_create(
        telegram_id=user.id,
        defaults={
            'telegram_username': user.username,
            'name': user.first_name or 'Аноним'
        }
    )

    try:
        payment = Payment.create({
            "amount": {"value": str(amount), "currency": "RUB"},
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/{settings.TG_BOT_USERNAME}"
            },
            "description": f"Донат на {event.title}",
            "metadata": {
                "user_id": user.id,
                "event_id": event.id
            }
        }, str(uuid.uuid4()))

        Donation.objects.create(
            event=event,
            participant=participant,
            amount=amount,
            payment_id=payment.id,
            is_confirmed=True
        )

        context.bot.send_message(
            chat_id=chat_id,
            text=f"✨ <b>Спасибо, что решили поддержать мероприятие, {user.first_name}!</b>\n\n"
                 f"Ваш донат {amount}₽ — это:\n"
                 f"• ☕ 10 чашек кофе для спикеров\n"
                 f"• 📚 Новые материалы для участников\n"
                 f"• 💻 Лучшее оборудование для трансляций\n\n"
                 f"<i>Спасибо за вклад в развитие комьюнити!</i>",
            parse_mode='HTML'
        )

        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(
            "💳 Перейти к оплате",
            url=payment.confirmation.confirmation_url
        )]])

        message = f"<b>Для оплаты {amount} ₽</b>\nНажмите кнопку ниже:"
        if update.callback_query:
            update.callback_query.edit_message_text(
                message, reply_markup=reply_markup, parse_mode='HTML')
        else:
            context.bot.send_message(
                chat_id, message, reply_markup=reply_markup, parse_mode='HTML')

    except Exception as e:
        error_msg = f"❌ <b>Ошибка при создании платежа</b>\n{str(e)}"
        if update.callback_query:
            update.callback_query.edit_message_text(
                error_msg, parse_mode='HTML')
        else:
            context.bot.send_message(chat_id, error_msg, parse_mode='HTML')


def current_speaker(update, context):
    event = Event.objects.filter(is_active=True).first()
    if not event:
        update.message.reply_text(
            "📭 Сейчас нет активных мероприятий",
            parse_mode='HTML'
        )
        return

    now = timezone.localtime(timezone.now())
    current_slot = event.get_current_speaker()

    if current_slot:
        speaker = current_slot.speaker
        start_time = timezone.localtime(current_slot.start_time)
        end_time = timezone.localtime(current_slot.end_time)

        # Добавляем пометку о продленном выступлении
        extended_note = " (выступление продлено организатором)" if current_slot.is_extended else ""

        update.message.reply_text(
            f"🎤 <b>Сейчас выступает:</b>{extended_note}\n\n"
            f"👤 <b>{speaker.name}</b>\n"
            f"📢 <i>{current_slot.title}</i>\n"
            f"🕒 {start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')}\n\n"
            f"{current_slot.description}\n\n"
            f"ℹ️ {speaker.bio if speaker.bio else 'Нет дополнительной информации'}",
            parse_mode='HTML'
        )
    else:
        update.message.reply_text(
            "⏳ <b>Сейчас перерыв или выступление не запланировано</b>\n\n"
            "Следующее выступление смотрите в программе",
            parse_mode='HTML'
        )


def get_ask_speaker_keyboard(speakers):
    """Клавиатура для выбора спикера с отметкой текущего"""
    keyboard = []
    event = Event.objects.filter(is_active=True).first()
    current_speaker = event.get_current_speaker(
    ).speaker if event and event.get_current_speaker() else None

    for speaker in speakers:
        if speaker.telegram_username:
            # Добавляем отметку если это текущий спикер
            speaker_label = f"🎤 {speaker.name} (сейчас выступает)" if current_speaker and speaker.id == current_speaker.id else speaker.name
            keyboard.append(
                [InlineKeyboardButton(
                    speaker_label, callback_data=f"ask_{speaker.telegram_username}")]
            )

    keyboard.append([InlineKeyboardButton("Назад", callback_data='back')])
    return InlineKeyboardMarkup(keyboard)


def ask_speaker_start(update, context):
    """Начало процесса задания вопроса"""
    event = Event.objects.filter(is_active=True).first()
    if not event:
        update.message.reply_text("Сейчас нет активных мероприятий")
        return ConversationHandler.END

    speakers = event.speakers.all()
    if not speakers:
        update.message.reply_text("На этом мероприятии нет спикеров")
        return ConversationHandler.END

    update.message.reply_text(
        "Выберите спикера для вопроса:",
        reply_markup=get_ask_speaker_keyboard(speakers)
    )
    return SELECTING_SPEAKER


def ask_speaker_select(update, context):
    """Обработка выбора спикера"""
    query = update.callback_query
    query.answer()

    if query.data == 'back':
        user = query.from_user
        try:
            participant = Participant.objects.get(telegram_id=user.id)
            query.edit_message_text(
                "Выберите действие:", reply_markup=get_main_keyboard(participant))
        except Participant.DoesNotExist:
            query.edit_message_text("❌ Пожалуйста, начните с команды /start")
        return ConversationHandler.END

    speaker_username = query.data.split('_', 1)[1]

    try:
        speaker = Speaker.objects.get(telegram_username=speaker_username)
        context.user_data['speaker_username'] = speaker_username
        # Сохраняем ID для надежности
        context.user_data['speaker_id'] = speaker.id
    except Speaker.DoesNotExist:
        query.edit_message_text("❌ Спикер не найден")
        return ConversationHandler.END

    context.user_data['speaker_username'] = speaker_username

    query.edit_message_text(
        "✍️ Введите ваш вопрос:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Отмена", callback_data='cancel')]
        ])
    )
    return AWAITING_QUESTION


def ask_speaker_receive_question(update, context):
    """Получение вопроса от пользователя"""
    question_text = update.message.text
    context.user_data['question_text'] = question_text

    update.message.reply_text(
        f"Подтвердите ваш вопрос:\n\n{question_text}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Подтвердить", callback_data='confirm')],
            [InlineKeyboardButton("❌ Отмена", callback_data='cancel')]
        ])
    )
    return CONFIRMING_QUESTION


def ask_speaker_confirm(update, context):
    """Подтверждение вопроса"""
    query = update.callback_query
    query.answer()

    if query.data == 'confirm':
        try:
            speaker_username = context.user_data['speaker_username']

            # Ищем спикера только по telegram_username
            speaker = Speaker.objects.get(telegram_username=speaker_username)

            if not speaker.telegram_id:
                query.edit_message_text(
                    "❌ Ошибка: у спикера не указан Telegram ID")
                return ConversationHandler.END

            result = send_question(
                speaker_username=speaker_username,
                participant_id=update.effective_user.id,
                participant_name=update.effective_user.first_name,
                text=context.user_data['question_text']
            )
            query.edit_message_text("✅ Вопрос успешно отправлен спикеру")
        except Exception as e:
            query.edit_message_text(f"❌ Ошибка при отправке вопроса: {str(e)}")
    else:
        query.edit_message_text("❌ Вопрос отменен")

    return ConversationHandler.END


def ask_speaker_cancel(update, context):
    """Отмена вопроса"""
    query = update.callback_query
    query.answer()
    query.edit_message_text("❌ Вопрос отменен")
    return ConversationHandler.END


def setup_speaker_handlers(dp):
    # Обработчик для кнопки "Ответить на вопрос"
    dp.add_handler(CallbackQueryHandler(
        handle_mark_answered,
        pattern='^answer_\\d+$'  # answer_<question_id>
    ))


def handle_mark_answered(update, context):
    query = update.callback_query
    question_id = int(query.data.split('_')[1])
    user = query.from_user

    try:
        question = Question.objects.get(
            id=question_id,
            speaker__telegram_id=user.id  # Проверяем, что отвечает именно спикер
        )
        question.mark_answered()
        query.edit_message_text("✅ Вопрос отмечен как отвеченный")
    except Question.DoesNotExist:
        query.edit_message_text("❌ Вопрос не найден или у вас нет прав")


def show_unanswered_questions(update, context):
    user = update.effective_user
    try:
        speaker = Speaker.objects.get(telegram_username=user.username)
        questions = speaker.questions.filter(is_answered=False)

        if not questions.exists():
            update.message.reply_text("У вас нет неотвеченных вопросов.")
            return

        for q in questions:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "✅ Ответил",
                    callback_data=f"answer_{q.id}"
                )]
            ])
            update.message.reply_text(
                f"❓ Вопрос от {q.participant.name}:\n\n"
                f"{q.text}\n\n"
                f"Задан: {q.timestamp.strftime('%d.%m.%Y %H:%M')}",
                reply_markup=keyboard
            )
    except Speaker.DoesNotExist:
        update.message.reply_text("Вы не зарегистрированы как спикер.")


def get_events_keyboard():
    """Клавиатура с активными и будущими мероприятиями"""
    events = Event.objects.filter(date__gte=timezone.now()).order_by('date')
    keyboard = [
        [InlineKeyboardButton(
            event.get_full_name(),
            callback_data=f"event_{event.id}"
        )]
        for event in events
    ]
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data='cancel')])
    return InlineKeyboardMarkup(keyboard)


def register_speaker_start(update, context):
    """Начало процесса регистрации спикера"""
    user = update.effective_user
    try:
        participant = Participant.objects.get(telegram_id=user.id)
    except Participant.DoesNotExist:
        update.message.reply_text(
            "❌ Пожалуйста, начните с команды /start",
            parse_mode='HTML',
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    events = Event.objects.filter(date__gte=timezone.now()).exists()

    if not events:
        update.message.reply_text(
            "Сейчас нет запланированных мероприятий",
            reply_markup=get_main_keyboard(participant)
        )
        return ConversationHandler.END

    update.message.reply_text(
        "Выберите мероприятие для регистрации:",
        reply_markup=get_events_keyboard()
    )
    return SELECTING_EVENT


def register_speaker_select_event(update, context):
    """Обработка выбора мероприятия"""
    query = update.callback_query
    query.answer()

    if query.data == 'cancel':
        query.edit_message_text("Регистрация отменена")
        return ConversationHandler.END

    event_id = int(query.data.split('_')[1])
    event = Event.objects.get(id=event_id)
    context.user_data['register_event'] = event

    query.edit_message_text(
        f"Подтвердите регистрацию как спикера на:\n"
        f"<b>{event.title}</b>\n"
        f"Дата: {event.date.strftime('%d.%m.%Y')}\n\n"
        f"Ваше имя: {query.from_user.full_name}\n"
        f"Username: @{query.from_user.username or 'не указан'}",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Подтвердить", callback_data='confirm')],
            [InlineKeyboardButton("❌ Отмена", callback_data='cancel')]
        ])
    )
    return CONFIRMING_REGISTRATION


def register_speaker_confirm(update, context):
    """Завершение регистрации"""
    query = update.callback_query
    query.answer()
    user = query.from_user

    if query.data == 'confirm':
        try:
            event = context.user_data['register_event']

            # Создаем или обновляем спикера
            speaker, created = Speaker.objects.update_or_create(
                telegram_id=user.id,
                defaults={
                    'name': user.full_name,
                    'telegram_username': user.username
                }
            )

            # Добавляем связь с мероприятием
            speaker.events.add(event)

            # Помечаем участника как спикера
            Participant.objects.update_or_create(
                telegram_id=user.id,
                defaults={
                    'name': user.full_name,
                    'telegram_username': user.username,
                    'is_speaker': True
                }
            )

            query.edit_message_text(
                f"✅ Вы успешно зарегистрированы как спикер на мероприятие:\n"
                f"<b>{event.title}</b>\n"
                f"Дата: {event.date.strftime('%d.%m.%Y')}",
                parse_mode='HTML'
            )
        except Exception as e:
            query.edit_message_text(f"❌ Ошибка регистрации: {str(e)}")
    else:
        query.edit_message_text("Регистрация отменена")

    return ConversationHandler.END


def subscribe_start(update, context):
    """Начало процесса подписки на рассылку"""
    user = update.effective_user

    try:
        participant = Participant.objects.get(telegram_id=user.id)

        if participant.is_subscribed:
            update.message.reply_text(
                "✅ <b>Вы уже подписаны на рассылку!</b>",
                parse_mode='HTML',
                reply_markup=get_main_keyboard(participant)
            )
            return ConversationHandler.END

        update.message.reply_text(
            "📬 <b>Хотите подписаться на рассылку?</b>\n"
            "Вы будете получать анонсы мероприятий и важные обновления.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "✅ Подтвердить", callback_data='subscribe_confirm')],
                [InlineKeyboardButton(
                    "❌ Отмена", callback_data='subscribe_cancel')]
            ])
        )
        return SUBSCRIBING

    except Participant.DoesNotExist:
        update.message.reply_text(
            "❌ <b>Ошибка: Вы не зарегистрированы как участник.</b>\n"
            "Пожалуйста, начните с команды /start, чтобы зарегистрироваться.",
            parse_mode='HTML',
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END


def subscribe_confirm(update, context):
    """Подтверждение подписки"""
    query = update.callback_query
    query.answer()
    user = query.from_user
    chat_id = query.message.chat_id

    if query.data == 'subscribe_confirm':
        try:
            participant = Participant.objects.get(telegram_id=user.id)
            participant.is_subscribed = True
            participant.save()
            query.edit_message_text(  # Edit to clear inline buttons
                "✅ Подписка подтверждена",
                parse_mode='HTML'
            )
            context.bot.send_message(
                chat_id=chat_id,
                text="✅ <b>Вы успешно подписаны на рассылку!</b>\n"
                     "Теперь вы будете получать наши анонсы и обновления.",
                parse_mode='HTML',
                reply_markup=get_main_keyboard(participant)
            )
        except Participant.DoesNotExist:
            query.edit_message_text(
                "❌ Подписка не выполнена",
                parse_mode='HTML'
            )
            context.bot.send_message(
                chat_id=chat_id,
                text="❌ <b>Ошибка: Вы не зарегистрированы как участник.</b>\n"
                     "Пожалуйста, начните с команды /start, чтобы зарегистрироваться.",
                parse_mode='HTML',
                reply_markup=ReplyKeyboardRemove()
            )
    else:
        try:
            participant = Participant.objects.get(telegram_id=user.id)
            context.bot.send_message(
                chat_id=chat_id,
                text="❌ Действие отменено",
                parse_mode='HTML',
                reply_markup=get_main_keyboard(participant)
            )
        except Participant.DoesNotExist:
            query.edit_message_text(
                "❌ Действие отменено",
                parse_mode='HTML'
            )
            context.bot.send_message(
                chat_id=chat_id,
                text="❌ Пожалуйста, начните с команды /start",
                parse_mode='HTML',
                reply_markup=ReplyKeyboardRemove()
            )

    return ConversationHandler.END


def mailing_start(update, context):
    """Начало процесса создания рассылки"""
    query = update.callback_query
    user = update.effective_user
    try:
        participant = Participant.objects.get(telegram_id=user.id)

        if not (participant.is_speaker or participant.is_manager):
            update.message.reply_text(
                "❌ <b>У вас нет прав для создания рассылки.</b>\n"
                "Эта функция доступна только спикерам и менеджерам.",
                parse_mode='HTML',
                reply_markup=get_main_keyboard(participant)
            )
            return ConversationHandler.END

        update.message.reply_text(
            "📣 <b>Введите текст рассылки:</b>\n"
            "Сообщение будет отправлено всем подписанным участникам.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "❌ Отмена", callback_data='mailing_cancel')]
            ])
        )
    except Participant.DoesNotExist:
        query.edit_message_text(
            "❌ Пожалуйста, начните с команды /start",
            parse_mode='HTML',
            reply_markup=ReplyKeyboardRemove()
        )

    return MAILING


def mailing_receive_message(update, context):
    """Получение текста рассылки"""
    mailing_text = update.message.text
    context.user_data['mailing_text'] = mailing_text

    update.message.reply_text(
        f"Подтвердите текст рассылки:\n\n{mailing_text}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "✅ Отправить", callback_data='mailing_confirm')],
            [InlineKeyboardButton("❌ Отмена", callback_data='mailing_cancel')]
        ])
    )
    return CONFIRMING_MAILING


def mailing_confirm(update, context):
    """Подтверждение и отправка рассылки"""
    query = update.callback_query
    query.answer()
    user = query.from_user
    chat_id = query.message.chat_id

    if query.data == 'mailing_confirm':
        try:
            participant = Participant.objects.get(telegram_id=user.id)
            mailing_text = context.user_data['mailing_text']
            subscribed_participants = Participant.objects.filter(
                is_subscribed=True)

            if not subscribed_participants.exists():
                query.edit_message_text(
                    "❌ Нет подписчиков",
                    parse_mode='HTML'
                )
                context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ <b>Нет подписчиков для рассылки.</b>",
                    parse_mode='HTML',
                    reply_markup=get_main_keyboard(participant)
                )
                return ConversationHandler.END

            sent_count = 0
            for participant in subscribed_participants:
                try:
                    context.bot.send_message(
                        chat_id=participant.telegram_id,
                        text=f"📢 <b>Новое сообщение от организаторов:</b>\n\n{mailing_text}",
                        parse_mode='HTML'
                    )
                    sent_count += 1
                except Exception as e:
                    print(
                        f"Failed to send message to {participant.telegram_id}: {str(e)}")

            query.edit_message_text(
                "✅ Рассылка отправлена",
                parse_mode='HTML'
            )
            context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ <b>Рассылка успешно отправлена {sent_count} подписчикам!</b>",
                parse_mode='HTML',
                reply_markup=get_main_keyboard(participant)
            )
        except Participant.DoesNotExist:
            query.edit_message_text(
                "❌ Ошибка рассылки",
                parse_mode='HTML'
            )
            context.bot.send_message(
                chat_id=chat_id,
                text="❌ Пожалуйста, начните с команды /start",
                parse_mode='HTML',
                reply_markup=ReplyKeyboardRemove()
            )
        except Exception as e:
            try:
                participant = Participant.objects.get(telegram_id=user.id)
                query.edit_message_text(
                    "❌ Ошибка рассылки",
                    parse_mode='HTML'
                )
                context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ <b>Ошибка при отправке рассылки:</b> {str(e)}",
                    parse_mode='HTML',
                    reply_markup=get_main_keyboard(participant)
                )
            except Participant.DoesNotExist:
                query.edit_message_text(
                    "❌ Ошибка рассылки",
                    parse_mode='HTML'
                )
                context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Пожалуйста, начните с команды /start",
                    parse_mode='HTML',
                    reply_markup=ReplyKeyboardRemove()
                )
    else:
        try:
            participant = Participant.objects.get(telegram_id=user.id)
            context.bot.send_message(
                chat_id=chat_id,
                text="❌ Действие отменено",
                parse_mode='HTML',
                reply_markup=get_main_keyboard(participant)
            )
        except Participant.DoesNotExist:
            query.edit_message_text(
                "❌ Действие отменено",
                parse_mode='HTML'
            )
            context.bot.send_message(
                chat_id=chat_id,
                text="❌ Пожалуйста, начните с команды /start",
                parse_mode='HTML',
                reply_markup=ReplyKeyboardRemove()
            )

    return ConversationHandler.END


def unsubscribe_start(update, context):
    """Начало процесса отписки от рассылки"""
    user = update.effective_user

    try:
        participant = Participant.objects.get(telegram_id=user.id)

        if not participant.is_subscribed:
            update.message.reply_text(
                "✅ <b>Вы не подписаны на рассылку!</b>",
                parse_mode='HTML',
                reply_markup=get_main_keyboard(participant)
            )
            return ConversationHandler.END

        update.message.reply_text(
            "📬 <b>Хотите отписаться от рассылки?</b>\n"
            "Вы больше не будете получать анонсы мероприятий и обновления.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "✅ Подтвердить", callback_data='unsubscribe_confirm')],
                [InlineKeyboardButton(
                    "❌ Отмена", callback_data='unsubscribe_cancel')]
            ])
        )
        return UNSUBSCRIBING

    except Participant.DoesNotExist:
        update.message.reply_text(
            "❌ <b>Ошибка: Вы не зарегистрированы как участник.</b>\n"
            "Пожалуйста, начните с команды /start, чтобы зарегистрироваться.",
            parse_mode='HTML',
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END


def unsubscribe_confirm(update, context):
    """Подтверждение отписки"""
    query = update.callback_query
    query.answer()
    user = query.from_user
    chat_id = query.message.chat_id

    if query.data == 'unsubscribe_confirm':
        try:
            participant = Participant.objects.get(telegram_id=user.id)
            participant.is_subscribed = False
            participant.save()
            query.edit_message_text(  # Edit to clear inline buttons
                "✅ Отписка подтверждена",
                parse_mode='HTML'
            )
            context.bot.send_message(
                chat_id=chat_id,
                text="✅ <b>Вы успешно отписались от рассылки!</b>\n"
                     "Вы больше не будете получать наши анонсы и обновления.",
                parse_mode='HTML',
                reply_markup=get_main_keyboard(participant)
            )
        except Participant.DoesNotExist:
            query.edit_message_text(
                "❌ Отписка не выполнена",
                parse_mode='HTML'
            )
            context.bot.send_message(
                chat_id=chat_id,
                text="❌ Пожалуйста, начните с команды /start",
                parse_mode='HTML',
                reply_markup=ReplyKeyboardRemove()
            )
    else:
        try:
            participant = Participant.objects.get(telegram_id=user.id)
            context.bot.send_message(
                chat_id=chat_id,
                text="❌ Действие отменено",
                parse_mode='HTML',
                reply_markup=get_main_keyboard(participant)
            )
        except Participant.DoesNotExist:
            query.edit_message_text(
                "❌ Действие отменено",
                parse_mode='HTML'
            )
            context.bot.send_message(
                chat_id=chat_id,
                text="❌ Пожалуйста, начните с команды /start",
                parse_mode='HTML',
                reply_markup=ReplyKeyboardRemove()
            )

    return ConversationHandler.END


def register_participant_start(update, context):
    """Начало процесса регистрации участника"""
    user = update.effective_user
    try:
        participant = Participant.objects.get(telegram_id=user.id)
    except Participant.DoesNotExist:
        update.message.reply_text(
            "❌ Пожалуйста, начните с команды /start",
            parse_mode='HTML',
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    events = Event.objects.filter(date__gte=timezone.now()).order_by('date')
    if not events.exists():
        update.message.reply_text(
            "📭 Сейчас нет запланированных мероприятий",
            parse_mode='HTML',
            reply_markup=get_main_keyboard(participant)
        )
        return ConversationHandler.END

    update.message.reply_text(
        "📌 Выберите мероприятие для регистрации:",
        reply_markup=get_events_keyboard()
    )
    return SELECTING_EVENT_PARTICIPANT


def register_participant_select_event(update, context):
    """Обработка выбора мероприятия для регистрации участника"""
    query = update.callback_query
    query.answer()

    if query.data == 'cancel':
        try:
            participant = Participant.objects.get(
                telegram_id=query.from_user.id)
            query.edit_message_text(
                "❌ Регистрация отменена",
                parse_mode='HTML'
            )
            context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ Действие отменено",
                parse_mode='HTML',
                reply_markup=get_main_keyboard(participant)
            )
        except Participant.DoesNotExist:
            query.edit_message_text(
                "❌ Пожалуйста, начните с команды /start",
                parse_mode='HTML'
            )
        return ConversationHandler.END

    event_id = int(query.data.split('_')[1])
    try:
        event = Event.objects.get(id=event_id)
        context.user_data['participant_event'] = event
        participant = Participant.objects.get(telegram_id=query.from_user.id)

        if event in participant.registered_events.all():
            query.edit_message_text(
                f"✅ Вы уже зарегистрированы на:\n"
                f"<b>{event.title}</b>\n"
                f"Дата: {event.date.strftime('%d.%m.%Y')}",
                parse_mode='HTML'
            )
            context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Выберите действие:",
                parse_mode='HTML',
                reply_markup=get_main_keyboard(participant)
            )
            return ConversationHandler.END

        query.edit_message_text(
            f"Подтвердите регистрацию как участника на:\n"
            f"<b>{event.title}</b>\n"
            f"Дата: {event.date.strftime('%d.%m.%Y')}\n\n"
            f"Ваше имя: {query.from_user.full_name}\n"
            f"Username: @{query.from_user.username or 'не указан'}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "✅ Подтвердить", callback_data='confirm')],
                [InlineKeyboardButton("❌ Отмена", callback_data='cancel')]
            ])
        )
        return CONFIRMING_PARTICIPANT_REGISTRATION
    except Event.DoesNotExist:
        query.edit_message_text("❌ Мероприятие не найдено")
        return ConversationHandler.END


def register_participant_confirm(update, context):
    """Завершение регистрации участника"""
    query = update.callback_query
    query.answer()
    user = query.from_user
    chat_id = query.message.chat_id

    if query.data == 'confirm':
        try:
            event = context.user_data['participant_event']
            participant, created = Participant.objects.update_or_create(
                telegram_id=user.id,
                defaults={
                    'name': user.full_name,
                    'telegram_username': user.username
                }
            )
            participant.registered_events.add(event)
            query.edit_message_text(
                f"✅ Вы успешно зарегистрированы как участник на мероприятие:\n"
                f"<b>{event.title}</b>\n"
                f"Дата: {event.date.strftime('%d.%m.%Y')}",
                parse_mode='HTML'
            )
            context.bot.send_message(
                chat_id=chat_id,
                text="✅ Регистрация завершена! Выберите действие:",
                parse_mode='HTML',
                reply_markup=get_main_keyboard(participant)
            )
        except Exception as e:
            query.edit_message_text(f"❌ Ошибка регистрации: {str(e)}")
    else:
        try:
            participant = Participant.objects.get(telegram_id=user.id)
            query.edit_message_text("❌ Регистрация отменена")
            context.bot.send_message(
                chat_id=chat_id,
                text="❌ Действие отменено",
                parse_mode='HTML',
                reply_markup=get_main_keyboard(participant)
            )
        except Participant.DoesNotExist:
            query.edit_message_text("❌ Пожалуйста, начните с команды /start")

    return ConversationHandler.END


def get_my_events_keyboard(participant):
    """Клавиатура с мероприятиями, на которые зарегистрирован участник"""
    events = participant.registered_events.all().order_by('date')
    keyboard = [
        [InlineKeyboardButton(
            event.get_full_name(),
            callback_data=f"my_event_{event.id}"
        )]
        for event in events
    ]
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data='cancel')])
    return InlineKeyboardMarkup(keyboard)


def my_events_start(update, context):
    """Начало процесса просмотра зарегистрированных мероприятий"""
    user = update.effective_user
    try:
        participant = Participant.objects.get(telegram_id=user.id)
    except Participant.DoesNotExist:
        update.message.reply_text(
            "❌ Пожалуйста, начните с команды /start",
            parse_mode='HTML',
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    events = participant.registered_events.all()
    if not events.exists():
        update.message.reply_text(
            "📭 Вы не зарегистрированы ни на одно мероприятие",
            parse_mode='HTML',
            reply_markup=get_main_keyboard(participant)
        )
        return ConversationHandler.END

    update.message.reply_text(
        "📋 <b>Ваши зарегистрированные мероприятия:</b>\n\n"
        "Выберите мероприятие, чтобы отписаться:",
        parse_mode='HTML',
        reply_markup=get_my_events_keyboard(participant)
    )
    return SHOW_MY_EVENTS


def my_events_select_event(update, context):
    """Обработка выбора мероприятия для отписки"""
    query = update.callback_query
    query.answer()

    if query.data == 'cancel':
        try:
            participant = Participant.objects.get(telegram_id=query.from_user.id)
            query.edit_message_text(
                "❌ Действие отменено",
                parse_mode='HTML'
            )
            context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ Действие отменено",
                parse_mode='HTML',
                reply_markup=get_main_keyboard(participant)
            )
        except Participant.DoesNotExist:
            query.edit_message_text(
                "❌ Пожалуйста, начните с команды /start",
                parse_mode='HTML'
            )
        return ConversationHandler.END

    event_id = int(query.data.split('_')[2])
    try:
        event = Event.objects.get(id=event_id)
        context.user_data['unregister_event'] = event
        participant = Participant.objects.get(telegram_id=query.from_user.id)

        query.edit_message_text(
            f"Подтвердите отписку от мероприятия:\n"
            f"<b>{event.title}</b>\n"
            f"Дата: {event.date.strftime('%d.%m.%Y')}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Подтвердить", callback_data='confirm')],
                [InlineKeyboardButton("❌ Отмена", callback_data='cancel')]
            ])
        )
        return CONFIRMING_UNREGISTER
    except Event.DoesNotExist:
        query.edit_message_text("❌ Мероприятие не найдено")
        return ConversationHandler.END


def my_events_confirm_unregister(update, context):
    """Подтверждение отписки от мероприятия"""
    query = update.callback_query
    query.answer()
    user = query.from_user
    chat_id = query.message.chat_id

    if query.data == 'confirm':
        try:
            event = context.user_data['unregister_event']
            participant = Participant.objects.get(telegram_id=user.id)
            if event in participant.registered_events.all():
                participant.registered_events.remove(event)
                query.edit_message_text(
                    f"✅ Вы успешно отписались от мероприятия:\n"
                    f"<b>{event.title}</b>\n"
                    f"Дата: {event.date.strftime('%d.%m.%Y')}",
                    parse_mode='HTML'
                )
            else:
                query.edit_message_text(
                    f"❌ Вы не зарегистрированы на:\n"
                    f"<b>{event.title}</b>",
                    parse_mode='HTML'
                )
            context.bot.send_message(
                chat_id=chat_id,
                text="Выберите действие:",
                parse_mode='HTML',
                reply_markup=get_main_keyboard(participant)
            )
        except Exception as e:
            query.edit_message_text(f"❌ Ошибка отписки: {str(e)}")
    else:
        try:
            participant = Participant.objects.get(telegram_id=user.id)
            query.edit_message_text("❌ Отписка отменена")
            context.bot.send_message(
                chat_id=chat_id,
                text="❌ Действие отменено",
                parse_mode='HTML',
                reply_markup=get_main_keyboard(participant)
            )
        except Participant.DoesNotExist:
            query.edit_message_text("❌ Пожалуйста, начните с команды /start")

    return ConversationHandler.END


def send_new_event_notification(bot, event):
    """Отправление подписчикам уведомлений о новых событиях"""

    subscribed_participants = Participant.objects.filter(is_subscribed=True)

    if not subscribed_participants.exists():
        print("No subscribed participants to notify about new event.")
        return 0

    sent_count = 0
    try:
        notification_text = (
            f"🎉 <b>Новое мероприятие анонсировано!</b>\n\n"
            f"📅 <b>{event.title}</b>\n"
            f"🕒 Дата: {event.date.strftime('%d.%m.%Y')}\n"
            f"📜 Программа:\n{event.get_program()}\n\n"
            f"<i>Зарегистрируйтесь или задайте вопросы спикерам через бота!</i>"
        )
    except Exception as e:
        print(f"Error generating notification text: {str(e)}")
        return 0

    for participant in subscribed_participants:
        try:
            bot.send_message(
                chat_id=participant.telegram_id,
                text=notification_text,
                parse_mode='HTML'
            )
            sent_count += 1
        except Exception as e:
            print(f"Не удалось отправить уведомление участнику с ID {participant.telegram_id}: {str(e)}")

    return sent_count


def networking(update, context):
    """Кнопка «Пообщаться» в главном меню"""
    user = update.message.from_user
    participant, _ = Participant.objects.get_or_create(
        telegram_id=user.id,
        defaults={
            'telegram_username': user.username,
            'name': user.first_name or 'Аноним'
        }
    )

    text = (
        "🌟 <b>Знакомства на мероприятии</b> 🌟\n\n"
        "Здесь можно:\n"
        "• Рассказать о себе\n"
        "• Найти интересных людей\n\n"
        "Как это работает?\n"
        "1. Заполните свою анкету.\n"
        "2. Смотрите анкеты других.\n"
        "3. Запрашивайте контакты понравившихся участников!"
    )

    buttons = []
    if not participant.bio:  # Проверяем, заполнена ли анкета
        buttons.append([InlineKeyboardButton("📝 Рассказать о себе", callback_data="fill_profile")])
    buttons.append([InlineKeyboardButton("👀 Познакомиться", callback_data="view_profiles")])

    update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode='HTML'
    )


def start_fill_profile(update, context):
    query = update.callback_query
    query.answer()

    participant = Participant.objects.get(telegram_id=query.from_user.id)
    if participant.bio:  # Если анкета уже заполнена
        query.edit_message_text(
            "✅ Вы уже заполнили анкету!\n"
            "Хотите познакомиться с другими участниками?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👀 Познакомиться", callback_data="view_profiles")]
            ])
        )
        return ConversationHandler.END

    query.edit_message_text(
        "📝 <b>Расскажите о себе</b>\n\n"
        "Введите ваше имя (как к вам обращаться):",
        parse_mode='HTML'
    )
    return AWAITING_NAME


def save_name(update, context):
    name = update.message.text
    context.user_data['name'] = name

    update.message.reply_text(
        "💼 Теперь укажите ваш род деятельности (например, «Python-разработчик»):"
    )
    return AWAITING_BIO


def save_bio(update, context):
    bio = update.message.text
    user = update.message.from_user

    Participant.objects.filter(telegram_id=user.id).update(
        name=context.user_data['name'],
        bio=bio
    )

    update.message.reply_text(
        "✅ Анкета сохранена!\n"
        "Теперь другие участники смогут с вами познакомиться.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👀 Познакомиться", callback_data="view_profiles")]
        ])
    )
    return ConversationHandler.END


def view_profiles(update, context):
    query = update.callback_query
    query.answer()

    participant = Participant.objects.get(telegram_id=query.from_user.id)
    other_profiles = Participant.objects.exclude(telegram_id=query.from_user.id).filter(bio__isnull=False)

    if not other_profiles.exists():
        query.edit_message_text("😢 Пока нет анкет для просмотра.")
        return ConversationHandler.END

    # Получаем список всех подходящих профилей
    available_profiles = list(other_profiles)

    # Если в контексте нет списка просмотренных профилей, создаем его
    if 'viewed_profiles' not in context.user_data:
        context.user_data['viewed_profiles'] = []

    # Ищем профиль, который еще не был показан
    for profile in available_profiles:
        if profile.telegram_id not in context.user_data['viewed_profiles']:
            context.user_data['current_profile_id'] = profile.telegram_id
            context.user_data['viewed_profiles'].append(profile.telegram_id)

            text = (
                f"👤 <b>{profile.name}</b>\n"
                f"💼 {profile.bio}\n\n"
                f"Хотите связаться?"
            )

            try:
                query.edit_message_text(
                    text,
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("📩 Запросить контакт", callback_data="request_contact"),
                            InlineKeyboardButton("➡️ Дальше", callback_data="next_profile")
                        ]
                    ]),
                    parse_mode='HTML'
                )
                return VIEWING_PROFILE
            except Exception as e:
                print(f"Ошибка при редактировании сообщения: {e}")
                return VIEWING_PROFILE

    # Если все профили просмотрены
    context.user_data['viewed_profiles'] = []  # Сбрасываем список просмотренных
    query.edit_message_text("😢 Вы просмотрели все анкеты. Начнем сначала!")
    return view_profiles(update, context)  # Рекурсивно запускаем снова


def handle_profile_actions(update, context):
    query = update.callback_query
    query.answer()

    if query.data == "request_contact":
        profile = Participant.objects.get(telegram_id=context.user_data['current_profile_id'])
        query.edit_message_text(
            f"✉️ Контакт участника:\n"
            f"@{profile.telegram_username}" if profile.telegram_username else
            "❌ У участника не указан Telegram-username."
        )
        return ConversationHandler.END
    else:
        return view_profiles(update, context)


def back_to_menu(update, context):
    user = update.message.from_user
    participant, _ = Participant.objects.get_or_create(
        telegram_id=user.id,
        defaults={
            'telegram_username': user.username,
            'name': user.first_name or 'Аноним'
        }
    )
    update.message.reply_text(
        "Выберите действие:",
        reply_markup=get_main_keyboard(participant)
    )


def setup_dispatcher(dp):
    # Командные обработчики
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", start))
    dp.add_handler(CommandHandler("cancel", cancel))

    # ConversationHandler: Вопрос спикеру
    ask_speaker_conv = ConversationHandler(
        entry_points=[MessageHandler(Filters.regex('^❓ Задать вопрос спикеру$'), ask_speaker_start)],
        states={
            SELECTING_SPEAKER: [
                CallbackQueryHandler(ask_speaker_select, pattern='^ask_'),
                CallbackQueryHandler(ask_speaker_cancel, pattern='^back$'),
            ],
            AWAITING_QUESTION: [
                MessageHandler(Filters.text & ~Filters.command, ask_speaker_receive_question),
                CallbackQueryHandler(ask_speaker_cancel, pattern='^cancel$'),
            ],
            CONFIRMING_QUESTION: [
                CallbackQueryHandler(ask_speaker_confirm, pattern='^confirm$'),
                CallbackQueryHandler(ask_speaker_cancel, pattern='^cancel$'),
            ],
        },
        fallbacks=[
            CommandHandler('cancel', ask_speaker_cancel),
            CallbackQueryHandler(ask_speaker_cancel, pattern='^cancel$'),
        ],
        allow_reentry=True,
    )
    dp.add_handler(ask_speaker_conv)

    # ConversationHandler: Регистрация участника
    participant_registration_conv = ConversationHandler(
        entry_points=[MessageHandler(Filters.regex('^👤 Зарегистрироваться участником$'), register_participant_start)],
        states={
            SELECTING_EVENT_PARTICIPANT: [
                CallbackQueryHandler(register_participant_select_event, pattern='^event_'),
                CallbackQueryHandler(register_participant_confirm, pattern='^cancel$'),
            ],
            CONFIRMING_PARTICIPANT_REGISTRATION: [
                CallbackQueryHandler(register_participant_confirm),
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            MessageHandler(Filters.regex('^🔙 Назад$'), back_to_menu)
        ],
    )
    dp.add_handler(participant_registration_conv)

    # ConversationHandler: Регистрация спикера
    registration_conv = ConversationHandler(
        entry_points=[MessageHandler(Filters.regex('^🎤 Зарегистрироваться спикером$'), register_speaker_start)],
        states={
            SELECTING_EVENT: [
                CallbackQueryHandler(register_speaker_select_event, pattern='^event_'),
                CallbackQueryHandler(register_speaker_confirm, pattern='^cancel$'),
            ],
            CONFIRMING_REGISTRATION: [
                CallbackQueryHandler(register_speaker_confirm),
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            MessageHandler(Filters.regex('^🔙 Назад$'), back_to_menu)
        ],
    )
    dp.add_handler(registration_conv)

    # ConversationHandler: Мои мероприятия
    my_events_conv = ConversationHandler(
        entry_points=[MessageHandler(Filters.regex('^📋 Мои мероприятия$'), my_events_start)],
        states={
            SHOW_MY_EVENTS: [
                CallbackQueryHandler(my_events_select_event, pattern='^my_event_'),
                CallbackQueryHandler(my_events_confirm_unregister, pattern='^cancel$'),
            ],
            CONFIRMING_UNREGISTER: [
                CallbackQueryHandler(my_events_confirm_unregister),
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    dp.add_handler(my_events_conv)

    # ConversationHandler: Донаты (фикс и кастом)
    donate_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_custom_donate_callback, pattern='^donate_custom$')],
        states={
            CHOOSE_CUSTOM_AMOUNT: [MessageHandler(Filters.text & ~Filters.command, handle_custom_amount)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    dp.add_handler(donate_conv_handler)

    # ConversationHandler: Подписка
    subscribe_conv = ConversationHandler(
        entry_points=[MessageHandler(Filters.regex('^✅ Подписаться на рассылку$'), subscribe_start)],
        states={
            SUBSCRIBING: [
                CallbackQueryHandler(subscribe_confirm, pattern='^subscribe_(confirm|cancel)$'),
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(subscribe_confirm, pattern='^subscribe_cancel$'),
        ],
    )
    dp.add_handler(subscribe_conv)

    # ConversationHandler: Отписка
    unsubscribe_conv = ConversationHandler(
        entry_points=[MessageHandler(Filters.regex('^❌ Отписаться от рассылки$'), unsubscribe_start)],
        states={
            UNSUBSCRIBING: [
                CallbackQueryHandler(unsubscribe_confirm, pattern='^unsubscribe_(confirm|cancel)$'),
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(unsubscribe_confirm, pattern='^unsubscribe_cancel$'),
        ],
    )
    dp.add_handler(unsubscribe_conv)

    # ConversationHandler: Рассылка
    mailing_conv = ConversationHandler(
        entry_points=[MessageHandler(Filters.regex('^📢 Сделать рассылку$'), mailing_start)],
        states={
            MAILING: [
                MessageHandler(Filters.text & ~Filters.command, mailing_receive_message),
            ],
            CONFIRMING_MAILING: [
                CallbackQueryHandler(mailing_confirm, pattern='^mailing_(confirm|cancel)$'),
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(mailing_confirm, pattern='^mailing_cancel$'),
        ],
    )
    dp.add_handler(mailing_conv)

    # ConversationHandler: Нетворкинг
    networking_conv = ConversationHandler(
        entry_points=[
            MessageHandler(Filters.regex('^🙋 Пообщаться$'), networking),
            CallbackQueryHandler(start_fill_profile, pattern='^fill_profile$'),
            CallbackQueryHandler(view_profiles, pattern='^view_profiles$')
        ],
        states={
            AWAITING_NAME: [MessageHandler(Filters.text & ~Filters.command, save_name)],
            AWAITING_BIO: [MessageHandler(Filters.text & ~Filters.command, save_bio)],
            VIEWING_PROFILE: [CallbackQueryHandler(handle_profile_actions)]
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            MessageHandler(Filters.regex('^🔙 Назад$'), back_to_menu)
        ],
        allow_reentry=True
    )
    dp.add_handler(networking_conv)

    # Обработчики главного меню
    dp.add_handler(MessageHandler(Filters.regex('^📅 Мероприятие$'), event_menu))
    dp.add_handler(MessageHandler(Filters.regex('^📝 Регистрация$'), registration_menu))
    dp.add_handler(MessageHandler(Filters.regex('^🙋 Пообщаться$'), networking))  # на случай одиночного входа
    dp.add_handler(MessageHandler(Filters.regex('^🎁 Поддержать$'), donate))
    dp.add_handler(MessageHandler(Filters.regex('^❓ Мои вопросы$'), show_unanswered_questions))
    dp.add_handler(MessageHandler(Filters.regex('^📢 Сделать рассылку$'), mailing_start))

    # Подменю "Мероприятие"
    dp.add_handler(MessageHandler(Filters.regex('^📜 Программа$'), program))
    dp.add_handler(MessageHandler(Filters.regex('^📋 Мои мероприятия$'), my_events_start))
    dp.add_handler(MessageHandler(Filters.regex('^❓ Задать вопрос спикеру$'), ask_speaker_start))
    dp.add_handler(MessageHandler(Filters.regex('^🎤 Кто выступает сейчас\\?$'), current_speaker))
    dp.add_handler(MessageHandler(Filters.regex('^✅ Подписаться на рассылку$'), subscribe_start))
    dp.add_handler(MessageHandler(Filters.regex('^❌ Отписаться от рассылки$'), unsubscribe_start))
    dp.add_handler(MessageHandler(Filters.regex('^🔙 Назад$'), back_to_menu))

    # Подменю "Регистрация"
    dp.add_handler(MessageHandler(Filters.regex('^👤 Зарегистрироваться участником$'), register_participant_start))
    dp.add_handler(MessageHandler(Filters.regex('^🎤 Зарегистрироваться спикером$'), register_speaker_start))
    dp.add_handler(MessageHandler(Filters.regex('^🔙 Назад$'), back_to_menu))

    # Обработчики для спикеров
    setup_speaker_handlers(dp)
    # Обработчики для донатов
    dp.add_handler(CallbackQueryHandler(handle_fixed_donate_callback, pattern='^donate_\\d+$'))

    return dp


def start_bot():
    updater = Updater(settings.TG_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    updater.bot.set_my_commands([
        BotCommand("start", "Главное меню"),
        BotCommand("help", "Помощь по боту"),
        BotCommand("cancel", "Отмена текущего действия"),
    ])

    dp = setup_dispatcher(dp)
    updater.start_polling()
    updater.idle()
