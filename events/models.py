from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone

class Event(models.Model):
    RECURRENCE_CHOICES = (
        ('NONE', 'None'),
        ('DAILY', 'Daily'),
        ('WEEKLY', 'Weekly'),
    )

    title = models.CharField(max_length=100)
    start_datetime = models.DateTimeField()
    duration = models.IntegerField()  # in minutes
    recurrence = models.CharField(max_length=6, choices=RECURRENCE_CHOICES, default='NONE')
    recurrence_end = models.DateTimeField(null=True, blank=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.title} - {self.owner.username}"