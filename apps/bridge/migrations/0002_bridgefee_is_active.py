# Generated by Django 5.2.1 on 2025-06-24 12:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bridge', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='bridgefee',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
    ]
