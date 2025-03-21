# Generated by Django 5.1.4 on 2025-03-16 11:20

import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0003_order_have_profit'),
    ]

    operations = [
        migrations.CreateModel(
            name='ErrorOrders',
            fields=[
                ('error_order_uuid', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True)),
                ('id_type', models.CharField(default='', max_length=50)),
                ('id_value', models.CharField(default='', max_length=50)),
                ('data', models.JSONField(default=dict)),
            ],
        ),
    ]
