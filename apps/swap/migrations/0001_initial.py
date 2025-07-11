# Generated by Django 5.2.3 on 2025-06-18 17:33

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import uuid
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='MarketStats',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token_pair', models.CharField(max_length=20)),
                ('volume_24h', models.DecimalField(decimal_places=18, max_digits=30)),
                ('high_24h', models.DecimalField(decimal_places=18, max_digits=30)),
                ('low_24h', models.DecimalField(decimal_places=18, max_digits=30)),
                ('change_24h', models.DecimalField(decimal_places=2, max_digits=10)),
                ('last_updated', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='SwapToken',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('symbol', models.CharField(max_length=20, unique=True)),
                ('name', models.CharField(max_length=100)),
                ('contract_address', models.CharField(blank=True, max_length=42, null=True)),
                ('decimals', models.PositiveSmallIntegerField(default=18)),
                ('is_active', models.BooleanField(default=True)),
                ('logo_url', models.URLField(blank=True, null=True)),
                ('network', models.CharField(max_length=50)),
                ('min_swap_amount', models.DecimalField(decimal_places=18, default=Decimal('0'), max_digits=30)),
            ],
        ),
        migrations.CreateModel(
            name='SwapQuote',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('amount_in', models.DecimalField(decimal_places=18, max_digits=30, validators=[django.core.validators.MinValueValidator(0)])),
                ('amount_out', models.DecimalField(decimal_places=18, max_digits=30, validators=[django.core.validators.MinValueValidator(0)])),
                ('rate', models.DecimalField(decimal_places=18, max_digits=30, validators=[django.core.validators.MinValueValidator(0)])),
                ('fee_amount', models.DecimalField(decimal_places=18, max_digits=30, validators=[django.core.validators.MinValueValidator(0)])),
                ('valid_until', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('token_in', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='quotes_in', to='swap.swaptoken')),
                ('token_out', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='quotes_out', to='swap.swaptoken')),
            ],
        ),
        migrations.CreateModel(
            name='SwapRoute',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_active', models.BooleanField(default=True)),
                ('fee_percentage', models.DecimalField(decimal_places=2, default=Decimal('0.3'), max_digits=5)),
                ('min_amount_in', models.DecimalField(decimal_places=18, max_digits=30)),
                ('max_amount_in', models.DecimalField(decimal_places=18, max_digits=30)),
                ('token_in', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='routes_in', to='swap.swaptoken')),
                ('token_out', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='routes_out', to='swap.swaptoken')),
            ],
            options={
                'unique_together': {('token_in', 'token_out')},
            },
        ),
        migrations.CreateModel(
            name='SwapPrice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('price_usd', models.DecimalField(decimal_places=18, max_digits=30)),
                ('timestamp', models.DateTimeField(default=django.utils.timezone.now)),
                ('token', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='swap.swaptoken')),
            ],
            options={
                'indexes': [models.Index(fields=['token', '-timestamp'], name='swap_swappr_token_i_ccc4b6_idx')],
            },
        ),
        migrations.CreateModel(
            name='SwapAllowance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user_token', models.CharField(max_length=64)),
                ('contract_address', models.CharField(max_length=42)),
                ('allowance_amount', models.DecimalField(decimal_places=18, default=Decimal('0'), max_digits=30)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('token', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='swap.swaptoken')),
            ],
            options={
                'unique_together': {('user_token', 'token', 'contract_address')},
            },
        ),
        migrations.CreateModel(
            name='SwapTransaction',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('user_token', models.CharField(max_length=64)),
                ('tx_hash', models.CharField(blank=True, max_length=66, null=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('completed', 'Completed'), ('failed', 'Failed'), ('refunded', 'Refunded')], default='pending', max_length=20)),
                ('from_address', models.CharField(max_length=42)),
                ('to_address', models.CharField(max_length=42)),
                ('executed_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('quote', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='swap.swapquote')),
            ],
            options={
                'indexes': [models.Index(fields=['user_token'], name='swap_swaptr_user_to_330c11_idx'), models.Index(fields=['status'], name='swap_swaptr_status_2187bb_idx'), models.Index(fields=['tx_hash'], name='swap_swaptr_tx_hash_6e2d55_idx')],
            },
        ),
    ]
