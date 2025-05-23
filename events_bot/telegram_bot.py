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
    Update
)
from django.conf import settings
from events_bot.models import Event, Participant, Donation
from yookassa import Payment, Configuration
import uuid
from django.utils import timezone

from events_bot.views import get_staff_ids, send_question


(
    CHOOSE_CUSTOM_AMOUNT,

    SELECTING_SPEAKER,
    AWAITING_QUESTION,
    CONFIRMING_QUESTION
) = range(4)

# Инициализация ЮKassa
Configuration.account_id = settings.YOOKASSA_SHOP_ID
Configuration.secret_key = settings.YOOKASSA_SECRET_KEY


def get_main_keyboard():
    """Кнопки главного меню"""
    keyboard = [
        ["📅 Программа", "🎁 Поддержать"],
        ["🙋Пообщаться", "📋Задать вопрос спикеру"],
        ["Кто выступает сейчас?"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def start(update, context):
    user = update.message.from_user
    Participant.objects.get_or_create(
        telegram_id=user.id,
        defaults={
            'telegram_username': user.username,
            'name': user.first_name or 'Аноним'
        }
    )

    event = Event.objects.filter(is_active=True).first()
    event_name = event.title if event else "Python Meetup"

    # Главное меню с кнопками
    main_menu_keyboard = [
        ["📅 Программа", "🎁 Поддержать"],
        ["🙋Пообщаться", "📋Задать вопрос спикеру"],
        ["Кто выступает сейчас?"]
    ]

    update.message.reply_text(
        f"✨ <b>Привет, {user.first_name}!</b> ✨\n\n"
        f"Я бот для <i>{event_name}</i>\n"
        "Выбери действие:",
        reply_markup=ReplyKeyboardMarkup(
            main_menu_keyboard,
            resize_keyboard=True,
            one_time_keyboard=False
        ),
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
        [InlineKeyboardButton("✨ Другая сумма", callback_data='donate_custom')],
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
        query.edit_message_text("🙅‍♂️ Сейчас нет активных мероприятий для доната")
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
        query.edit_message_text("🙅‍♂️ Сейчас нет активных мероприятий для доната")
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

        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(
            "💳 Перейти к оплате",
            url=payment.confirmation.confirmation_url
        )]])

        message = f"<b>Оплата {amount}₽</b>\nНажмите кнопку ниже:"
        if update.callback_query:
            update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode='HTML')
        else:
            context.bot.send_message(chat_id, message, reply_markup=reply_markup, parse_mode='HTML')

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

    except Exception as e:
        error_msg = f"❌ <b>Ошибка при создании платежа</b>\n{str(e)}"
        if update.callback_query:
            update.callback_query.edit_message_text(error_msg, parse_mode='HTML')
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

    now = timezone.now()
    current_slot = event.get_current_speaker()

    if current_slot:
        speaker = current_slot.speaker
        update.message.reply_text(
            f"🎤 <b>Сейчас выступает:</b>\n\n"
            f"👤 <b>{speaker.name}</b>\n"
            f"📢 <i>{current_slot.title}</i>\n"
            f"🕒 {current_slot.start_time.strftime('%H:%M')}-{current_slot.end_time.strftime('%H:%M')}\n\n"
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
    """Клавиатура для выбора спикера"""
    keyboard = []
    for speaker in speakers:
        if speaker.telegram_username:
            keyboard.append(
                [InlineKeyboardButton(speaker.name, callback_data=f"ask_{speaker.telegram_username}")]
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
        query.edit_message_text("Выберите действие:", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    speaker_username = query.data.split('_', 1)[1]
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
            result = send_question(
                speaker_username=context.user_data['speaker_username'],
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


def setup_dispatcher(dp):
    # Обработчики команд
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", start))  # Помощь тоже ведет в стартовое меню

    # Обработчики текстовых сообщений (кнопки главного меню)
    dp.add_handler(MessageHandler(Filters.regex('^📅 Программа$'), program))
    dp.add_handler(MessageHandler(Filters.regex('^🎁 Поддержать$'), donate))
    dp.add_handler(MessageHandler(Filters.regex('^Кто выступает сейчас\?$'), current_speaker))

    # Обработчики вопросов к спикерам
    ask_speaker_conv = ConversationHandler(
        entry_points=[
            MessageHandler(Filters.regex('^📋Задать вопрос спикеру$'), ask_speaker_start)
        ],
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
    )

    dp.add_handler(ask_speaker_conv)

    # Обработчики донатов
    dp.add_handler(CallbackQueryHandler(handle_fixed_donate_callback, pattern='^donate_\\d+$'))

    donate_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_custom_donate_callback, pattern='^donate_custom$')],
        states={
            CHOOSE_CUSTOM_AMOUNT: [MessageHandler(Filters.text & ~Filters.command, handle_custom_amount)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    dp.add_handler(donate_conv_handler)

    return dp


def start_bot():
    updater = Updater(settings.TG_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    updater.bot.set_my_commands([
        BotCommand("start", "Главное меню"),
        BotCommand("program", "Программа мероприятия"),
        BotCommand("donate", "Поддержать мероприятие"),
        BotCommand("help", "Помощь по боту")
    ])

    dp = setup_dispatcher(dp)
    updater.start_polling()
    updater.idle()
