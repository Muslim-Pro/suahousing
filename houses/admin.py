from django.contrib import admin
from .models import House, Room

# Register your models here.

class RoomInline(admin.TabularInline):
    model = Room
    extra = 1  # Inakupa mstari mmoja wa kuanzia kuingiza chumba, unaweza kuongeza mingine

class HouseAdmin(admin.ModelAdmin):
    # 1. kolam zitakazoonekana kwenye orodha kuu upande wa admin
    list_display = ('title', 'location', 'is_available', 'landlord')
    
    # 2. iki ni kichujio cha pembeni upande wa kulia wa admin(Kitakusaidia kuchuja kwa eneo au kama chumba kiko wazi)
    list_filter = ('location', 'is_available')
    
    # 3. hii Sehemu ya kutafutia (Search bar itatokea juu, utatafuta kwa jina la nyumba au anwani)
    search_fields = ('title', 'address')
    
    # 4. Inakuwezesha kujaza vyumba hapo hapo unaposajili nyumba kuu
    inlines = [RoomInline]

# Kusajili model
admin.site.register(House, HouseAdmin)