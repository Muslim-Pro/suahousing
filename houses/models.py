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
    title = models.CharField(max_length=200, verbose_name="Jina la Nyumba/Hosteli")
    description = models.TextField(verbose_name="Maelezo ya Jumla ya Nyumba")
    location = models.CharField(max_length=50, choices=LOCATION_CHOICES, default='mazimbu', verbose_name="Eneo Ilipo")
    address = models.CharField(max_length=255, verbose_name="Anwani ya Karibu")
    image = models.ImageField(upload_to='house_images/', verbose_name="Picha ya Nje ya Nyumba")
    is_available = models.BooleanField(default=True, verbose_name="Ipo Wazi?")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class Room(models.Model):
    ROOM_TYPES = [
        ('master', 'Master Bedroom (Choo ndani)'),
        ('single', 'Single Room (Kawaida - Choo cha nje)'),
        ('double', 'Double Room (Chumba kikubwa/Sebule)'),
    ]

    house = models.ForeignKey(House, on_delete=models.CASCADE, related_name='rooms', verbose_name="Inapatikana kwenye Nyumba gani?")
    room_type = models.CharField(max_length=20, choices=ROOM_TYPES, verbose_name="Aina ya Chumba")
    price = models.IntegerField(verbose_name="Bei ya Chumba hiki")
    room_image = models.ImageField(upload_to='room_images/', verbose_name="Picha ya Ndani ya Chumba")
    description = models.CharField(max_length=255, blank=True, null=True, verbose_name="Sifa za ziada (mfano: Kina feni, vigae)")

    def __str__(self):
        return f"{self.get_room_type_display()} - {self.house.title} (TZS {self.price})"