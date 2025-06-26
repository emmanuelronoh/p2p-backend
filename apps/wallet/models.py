from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.utils import timezone
from datetime import timedelta
from encrypted_model_fields import fields
import uuid

User = get_user_model()

class Currency(models.Model):
    CURRENCY_TYPES = (
        ('fiat', 'Fiat'),
        ('crypto', 'Cryptocurrency'),
        ('token', 'Token'),
    )
    
    NETWORK_TYPES = (
        ('mainnet', 'Mainnet'),
        ('testnet', 'Testnet'),
    )
    
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=CURRENCY_TYPES)
    network = models.CharField(max_length=10, choices=NETWORK_TYPES, default='mainnet')
    contract_address = models.CharField(max_length=255, blank=True, null=True)  # For tokens
    is_active = models.BooleanField(default=True)
    min_withdrawal = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    min_deposit = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    withdrawal_fee = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    withdrawal_fee_type = models.CharField(max_length=10, choices=[('fixed', 'Fixed'), ('percent', 'Percentage')], default='fixed')
    deposit_enabled = models.BooleanField(default=True)
    withdrawal_enabled = models.BooleanField(default=True)
    trading_enabled = models.BooleanField(default=True)
    precision = models.PositiveSmallIntegerField(default=8)
    confirmations_required = models.PositiveSmallIntegerField(default=6)  # Blocks needed for confirmation
    icon_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.code} ({self.name})"

    class Meta:
        verbose_name_plural = "Currencies"
        indexes = [
            models.Index(fields=['code', 'is_active']),
            models.Index(fields=['type', 'is_active']),
        ]


class Wallet(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wallets')
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    locked = models.DecimalField(max_digits=20, decimal_places=8, default=0)  # For orders/withdrawals
    staked = models.DecimalField(max_digits=20, decimal_places=8, default=0)  # For staking
    interest_owed = models.DecimalField(max_digits=20, decimal_places=8, default=0)  # For savings/earn
    address = models.CharField(max_length=255, blank=True, null=True)  # Main deposit address
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'currency')
        verbose_name_plural = "Wallets"
        indexes = [
            models.Index(fields=['user', 'currency']),
        ]

    def __str__(self):
        return f"{self.user.username}'s {self.currency.code} Wallet"

    @property
    def available_balance(self):
        return self.balance - self.locked


class Transaction(models.Model):
    TRANSACTION_TYPES = (
        ('deposit', 'Deposit'),
        ('withdrawal', 'Withdrawal'),
        ('transfer', 'Transfer'),
        ('trade', 'Trade'),
        ('staking', 'Staking'),
        ('earning', 'Earning'),
        ('fee', 'Fee'),
        ('rebate', 'Rebate'),
        ('adjustment', 'Adjustment'),
    )
    
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('canceled', 'Canceled'),
        ('rejected', 'Rejected'),
        ('processing', 'Processing'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions', null=True, blank=True)
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=20, decimal_places=8, validators=[MinValueValidator(0)])
    fee = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    fee_currency = models.ForeignKey(Currency, on_delete=models.SET_NULL, null=True, blank=True, related_name='fee_transactions')
    type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    address = models.CharField(max_length=255, blank=True, null=True)
    memo = models.CharField(max_length=255, blank=True, null=True)
    txid = models.CharField(max_length=255, blank=True, null=True)
    confirmations = models.PositiveIntegerField(default=0)
    required_confirmations = models.PositiveIntegerField(default=6)
    network = models.CharField(max_length=50, blank=True, null=True)  # For multi-network support
    from_address = models.CharField(max_length=255, blank=True, null=True)
    to_address = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)  # For additional data
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['txid']),
            models.Index(fields=['created_at']),
            models.Index(fields=['currency', 'type']),
        ]

    def __str__(self):
        return f"{self.get_type_display()} - {self.amount} {self.currency.code} ({self.status})"

    def save(self, *args, **kwargs):
        if self.status == 'completed' and not self.completed_at:
            self.completed_at = timezone.now()
        super().save(*args, **kwargs)


class DepositAddress(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='deposit_addresses')
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    address = models.CharField(max_length=255)
    memo = models.CharField(max_length=255, blank=True, null=True)  # For XRP, EOS, etc.
    privkey = fields.EncryptedCharField(max_length=255, blank=True, null=True)  # Encrypted private key
    derivation_path = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_archived = models.BooleanField(default=False)
    label = models.CharField(max_length=100, blank=True, null=True)
    last_checked = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'currency', 'address', 'memo')
        verbose_name_plural = "Deposit Addresses"
        indexes = [
            models.Index(fields=['user', 'currency']),
            models.Index(fields=['address']),
        ]

    def __str__(self):
        return f"{self.user.username}'s {self.currency.code} Deposit Address"

    def get_balance(self):
        """Check actual blockchain balance for this address"""
        # This would be implemented with blockchain API calls
        return 0


class WithdrawalLimit(models.Model):
    PERIOD_CHOICES = (
        ('24h', '24 Hours'),
        ('7d', '7 Days'),
        ('30d', '30 Days'),
    )

    TIER_CHOICES = (
        (1, 'Tier 1 - Basic'),
        (2, 'Tier 2 - Verified'),
        (3, 'Tier 3 - Enhanced'),
        (4, 'Tier 4 - Institutional'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='withdrawal_limits')
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    period = models.CharField(max_length=5, choices=PERIOD_CHOICES, default='24h')
    tier = models.PositiveSmallIntegerField(choices=TIER_CHOICES, default=1)
    limit_amount = models.DecimalField(max_digits=20, decimal_places=8)
    used_amount = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    remaining_amount = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    updated_at = models.DateTimeField(auto_now=True)
    reset_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('user', 'currency', 'period')
        indexes = [
            models.Index(fields=['user', 'currency']),
        ]

    def __str__(self):
        return f"{self.user.username}'s {self.currency.code} {self.get_period_display()} Withdrawal Limit"

    def save(self, *args, **kwargs):
        self.remaining_amount = self.limit_amount - self.used_amount
        super().save(*args, **kwargs)


class ExchangeRate(models.Model):
    RATE_TYPES = (
        ('spot', 'Spot'),
        ('future', 'Future'),
        ('margin', 'Margin'),
    )

    base_currency = models.ForeignKey(Currency, on_delete=models.CASCADE, related_name='base_rates')
    quote_currency = models.ForeignKey(Currency, on_delete=models.CASCADE, related_name='quote_rates')
    rate = models.DecimalField(max_digits=20, decimal_places=8)
    rate_type = models.CharField(max_length=10, choices=RATE_TYPES, default='spot')
    is_active = models.BooleanField(default=True)
    source = models.CharField(max_length=50, default='internal')  # internal, binance, coinbase, etc.
    updated_at = models.DateTimeField(auto_now=True)
    valid_until = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = ('base_currency', 'quote_currency', 'rate_type')
        indexes = [
            models.Index(fields=['base_currency', 'quote_currency']),
        ]

    def __str__(self):
        return f"1 {self.base_currency.code} = {self.rate} {self.quote_currency.code} ({self.get_rate_type_display()})"


class NetworkFee(models.Model):
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    network = models.CharField(max_length=50)  # ERC20, TRC20, BEP20, etc.
    withdrawal_fee = models.DecimalField(max_digits=20, decimal_places=8)
    withdrawal_min = models.DecimalField(max_digits=20, decimal_places=8)
    deposit_enabled = models.BooleanField(default=True)
    withdrawal_enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('currency', 'network')
        verbose_name_plural = "Network Fees"

    def __str__(self):
        return f"{self.currency.code} ({self.network}) Fee"


class UserAddressBook(models.Model):
    ADDRESS_TYPES = (
        ('external', 'External Wallet'),
        ('internal', 'Internal Transfer'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='address_book')
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    address = models.CharField(max_length=255)
    memo = models.CharField(max_length=255, blank=True, null=True)
    address_type = models.CharField(max_length=10, choices=ADDRESS_TYPES, default='external')
    label = models.CharField(max_length=100)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'currency', 'address', 'memo')
        verbose_name_plural = "User Address Book"

    def __str__(self):
        return f"{self.user.username}'s {self.currency.code} Address ({self.label})"