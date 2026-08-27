from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        from django.contrib.auth.models import User

        from . import signals  # noqa: F401

        def _user_type(user):
            try:
                return user.profile.user_type
            except Exception:
                return ''

        if not hasattr(User, 'user_type'):
            User.add_to_class('user_type', property(_user_type))
