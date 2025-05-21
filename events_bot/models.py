from django.db import models
from django.utils import timezone


class Event(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()
    date = models.DateField(auto_now_add=False)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title

    def get_program(self):
        """Формирует программу мероприятия из слотов времени."""
        time_slots = self.time_slots.select_related('speaker').all()
        program = []
        for slot in time_slots:
            program.append(
                f"{slot.start_time.strftime('%H:%M')} - {slot.end_time.strftime('%H:%M')}: "
                f"{slot.title} ({slot.speaker.name})"
            )
        return "\n".join(program) if program else "Программа пока не доступна."

    def get_current_speaker(self):
        if not self.is_active:
            return None
        now = timezone.now()
        return self.time_slots.filter(
            start_time__lte=now,
            end_time__gte=now
        ).select_related('speaker').first()


class Speaker(models.Model):
    events = models.ManyToManyField(
        Event,
        related_name='speakers'
    )
    name = models.CharField(max_length=100)
    telegram_username = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )
    bio = models.TextField(
        blank=True,
        null=True
    )

    def __str__(self):
        return self.name


class TimeSlot(models.Model):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='time_slots'
    )
    speaker = models.ForeignKey(
        Speaker,
        on_delete=models.CASCADE,
        related_name='time_slots'
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['start_time']
        indexes = [
            models.Index(fields=['start_time', 'end_time']),
        ]

    def __str__(self):
        return f"{self.title} ({self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')})"


class Participant(models.Model):
    telegram_id = models.BigIntegerField(unique=True)
    telegram_username = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )
    name = models.CharField(max_length=100)
    bio = models.TextField(
        blank=True,
        null=True,
        help_text="Короткая информация о роде деятельности"
    )
    is_speaker = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} (@{self.telegram_username})"


class Question(models.Model):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='questions'
    )
    speaker = models.ForeignKey(
        Speaker,
        on_delete=models.CASCADE,
        related_name='questions'
    )
    participant = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name='questions'
    )
    text = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_answered = models.BooleanField(default=False)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"Вопрос от {self.participant.name} к {self.speaker.name}"


class Donation(models.Model):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='donations'
    )
    participant = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name='donations'
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"Донат {self.amount} от {self.participant.name}"


class ConnectionRequest(models.Model):
    participant = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name='connection_requests'
    )
    target_participant = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name='incoming_requests'
    )
    is_accepted = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['participant', 'target_participant']]
        ordering = ['-timestamp']

    def __str__(self):
        return f"Запрос на знакомство от {self.participant.name} к {self.target_participant.name}"
