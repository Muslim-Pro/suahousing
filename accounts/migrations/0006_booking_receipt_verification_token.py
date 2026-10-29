from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_booking_payment_phone_number_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='receipt_verification_token',
            field=models.UUIDField(
                blank=True,
                editable=False,
                null=True,
                unique=True,
            ),
        ),
    ]
