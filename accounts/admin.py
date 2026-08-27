from django.contrib import admin

from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'user_type', 'phone')
    list_filter = ('user_type',)
    search_fields = ('user__username', 'user__email', 'phone')
