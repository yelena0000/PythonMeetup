from django.db import models
from django.utils import timezone


class Event(models.Model):
    title = models.CharField(max_length=255, verbose_name="Название мероприятия")
    description = models.TextField(verbose_name="Описание")
    date = models.DateField(auto_now_add=False, verbose_name="Дата проведения")
    is_active = models.BooleanField(default=True, verbose_name="Активно")

    def __str__(self):
        return self.title

    def get_program(self):
        """Формирует программу мероприятия из слотов времени."""
        time_slots = self.time_slots.select_related('speaker').all()
        program = []
        for slot in time_slots:
            start_local = timezone.localtime(slot.start_time)
            end_local = timezone.localtime(slot.end_time)
            program.append(
                f"{start_local.strftime('%H:%M')} - {end_local.strftime('%H:%M')}: "
                f"{slot.title} ({slot.speaker.name})"
            )
        return "\n".join(program) if program else "Программа пока не доступна."

    def get_current_speaker(self):
        if not self.is_active:
            return None

        now = timezone.now()

        # Сначала проверяем слоты с продленным выступлением
        extended_slot = self.time_slots.filter(
            is_extended=True
        ).select_related('speaker').first()

        if extended_slot:
            return extended_slot

        # Если нет продленных выступлений, работаем по расписанию
        return self.time_slots.filter(
            start_time__lte=now,
            end_time__gte=now
        ).select_related('speaker').first()

    def get_full_name(self):
        return f"{self.title} ({self.date.strftime('%d.%m.%Y')})"

    class Meta:
        ordering = ['date']
        verbose_name = "Мероприятие"
        verbose_name_plural = "Мероприятия"


class Speaker(models.Model):
    events = models.ManyToManyField(
        Event,
        related_name='speakers',
        blank=True,
        verbose_name="Мероприятия"
    )
    name = models.CharField(max_length=100, verbose_name="Имя")
    telegram_username = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        unique=True,
        verbose_name="Telegram username"
    )
    telegram_id = models.BigIntegerField(
        unique=True,
        null=True,
        blank=True,
        help_text="ID пользователя в Telegram",
        verbose_name="Telegram ID"
    )
    bio = models.TextField(
        blank=True,
        null=True,
        verbose_name="Биография"
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Спикер"
        verbose_name_plural = "Спикеры"


class TimeSlot(models.Model):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='time_slots',
        verbose_name="Мероприятие"
    )
    speaker = models.ForeignKey(
        Speaker,
        on_delete=models.CASCADE,
        related_name='time_slots',
        verbose_name="Спикер"
    )
    start_time = models.DateTimeField(verbose_name="Время начала")
    end_time = models.DateTimeField(verbose_name="Время окончания")
    title = models.CharField(max_length=255, verbose_name="Название доклада")
    description = models.TextField(blank=True, verbose_name="Описание доклада")
    is_extended = models.BooleanField(
        default=False,
        verbose_name="Выступление продлено",
        help_text="Если отмечено, спикер будет считаться текущим вне зависимости от расписания"
    )

    class Meta:
        ordering = ['start_time']
        indexes = [
            models.Index(fields=['start_time', 'end_time']),
        ]
        verbose_name = "Временной слот"
        verbose_name_plural = "Временные слоты"

    def __str__(self):
        return f"{self.title} ({self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')})"


class Participant(models.Model):
    telegram_id = models.BigIntegerField(unique=True, verbose_name="Telegram ID")
    telegram_username = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Telegram username"
    )
    name = models.CharField(max_length=100, verbose_name="Имя")
    bio = models.TextField(
        blank=True,
        null=True,
        help_text="Короткая информация о роде деятельности",
        verbose_name="О себе"
    )
    is_speaker = models.BooleanField(default=False, verbose_name='Докладчик')
    is_event_manager = models.BooleanField(default=False, verbose_name='Организатор')
    is_subscribed = models.BooleanField(default=False, verbose_name='Подписан на рассылку')

    registered_events = models.ManyToManyField(
        Event,
        related_name='participants',
        blank=True,
        verbose_name='Зарегистрированные мероприятия'
    )

    @property
    def has_profile(self):
        """Проверяет, заполнена ли анкета"""
        return bool(self.name and self.bio)

    def __str__(self):
        return f"{self.name} (@{self.telegram_username})"

    class Meta:
        verbose_name = "Участник"
        verbose_name_plural = "Участники"


class Question(models.Model):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='questions',
        verbose_name="Мероприятие"
    )
    speaker = models.ForeignKey(
        Speaker,
        on_delete=models.CASCADE,
        related_name='questions',
        verbose_name="Спикер"
    )
    participant = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name='questions',
        verbose_name="Участник"
    )
    text = models.TextField(verbose_name="Текст вопроса")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Время создания")
    is_answered = models.BooleanField(default=False, verbose_name="Ответ получен")

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Вопрос"
        verbose_name_plural = "Вопросы"

    def __str__(self):
        return f"Вопрос от {self.participant.name} к {self.speaker.name}"

    def mark_answered(self):
        self.is_answered = True
        self.save()


class Donation(models.Model):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='donations',
        verbose_name="Мероприятие"
    )
    participant = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name='donations',
        verbose_name="Участник"
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Сумма"
    )
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Время доната")
    payment_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="ID платежа"
    )
    is_confirmed = models.BooleanField(default=False, verbose_name="Подтверждён")

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Донат"
        verbose_name_plural = "Донаты"

    def __str__(self):
        status = "✅" if self.is_confirmed else "⏳"
        return f"{status} Донат {self.amount}₽ от {self.participant.name}"


class ConnectionRequest(models.Model):
    participant = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name='connection_requests',
        verbose_name="Участник"
    )
    target_participant = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name='incoming_requests',
        verbose_name="Целевой участник"
    )
    is_accepted = models.BooleanField(default=False, verbose_name="Принят")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Время запроса")

    class Meta:
        unique_together = [['participant', 'target_participant']]
        ordering = ['-timestamp']
        verbose_name = "Запрос на знакомство"
        verbose_name_plural = "Запросы на знакомство"

    def __str__(self):
        return f"Запрос на знакомство от {self.participant.name} к {self.target_participant.name}"
