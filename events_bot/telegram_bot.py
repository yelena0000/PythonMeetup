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
    BotCommand
)
from django.conf import settings
from events_bot.models import Event, Participant, Donation
from yookassa import Payment, Configuration
import uuid

CHOOSE_CUSTOM_AMOUNT = range(1)

# Инициализация ЮKassa
Configuration.account_id = settings.YOOKASSA_SHOP_ID
Configuration.secret_key = settings.YOOKASSA_SECRET_KEY


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


def setup_dispatcher(dp):
    # Обработчики команд
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", start))  # Помощь тоже ведет в стартовое меню

    # Обработчики текстовых сообщений (кнопки главного меню)
    dp.add_handler(MessageHandler(Filters.regex('^📅 Программа$'), program))
    dp.add_handler(MessageHandler(Filters.regex('^🎁 Поддержать$'), donate))
    # тут будут обработчики для "Пообщаться" и "Задать вопрос"

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
