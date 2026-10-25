from django.db import models
from django.contrib.auth.models import User

# Create your models here.

class House(models.Model):
    LOCATION_CHOICES = [
        ('mazimbu', 'Mazimbu Campus'),
        ('moringe', 'Edward Moringe Campus Area'),
        ('chang_ombe', "Chang'ombe"),
        ('kingolwira', 'Kingolwira'),
        ('town', 'Morogoro Town'),
    ]

    landlord = models.ForeignKey(User, on_delete=models.CASCADE, related_name='houses')
    title = models.CharField(max_length=200, verbose_name="Property name")
    description = models.TextField(verbose_name="Property description")
    location = models.CharField(max_length=50, choices=LOCATION_CHOICES, default='mazimbu', verbose_name="Location")
    address = models.CharField(max_length=255, verbose_name="Nearby address")
    image = models.ImageField(upload_to='house_images/', verbose_name="Property exterior photo")
    is_available = models.BooleanField(default=True, verbose_name="Available")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class Room(models.Model):
    ROOM_TYPES = [
        ('master', 'Master bedroom (private bathroom)'),
        ('single', 'Single room (shared bathroom)'),
        ('double', 'Double room (large room / living area)'),
    ]

    house = models.ForeignKey(House, on_delete=models.CASCADE, related_name='rooms', verbose_name="Property")
    room_type = models.CharField(max_length=20, choices=ROOM_TYPES, verbose_name="Room type")
    price = models.IntegerField(verbose_name="Room price")
    room_image = models.ImageField(upload_to='room_images/', verbose_name="Room photo")
    description = models.CharField(max_length=255, blank=True, null=True, verbose_name="Additional features (e.g. fan, tiled floor)")

    def __str__(self):
        return f"{self.get_room_type_display()} - {self.house.title} (TZS {self.price})"