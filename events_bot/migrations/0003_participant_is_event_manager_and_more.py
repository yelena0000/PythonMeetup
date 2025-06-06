# Generated by Django 4.2.20 on 2025-05-23 08:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events_bot', '0002_donation_is_confirmed_donation_payment_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='participant',
            name='is_event_manager',
            field=models.BooleanField(default=False, verbose_name='Управляющий мероприятием'),
        ),
        migrations.AlterField(
            model_name='participant',
            name='is_speaker',
            field=models.BooleanField(default=False, verbose_name='Докладчик'),
        ),
        migrations.AlterField(
            model_name='speaker',
            name='events',
            field=models.ManyToManyField(blank=True, related_name='speakers', to='events_bot.event'),
        ),
    ]
