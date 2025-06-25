from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator

User = get_user_model()

class Currency(models.Model):
    CURRENCY_TYPES = (
        ('fiat', 'Fiat'),
        ('crypto', 'Cryptocurrency'),
        ('token', 'Token'),
    )
    
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=CURRENCY_TYPES)
    is_active = models.BooleanField(default=True)
    min_withdrawal = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    withdrawal_fee = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    precision = models.PositiveSmallIntegerField(default=8)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.code} ({self.name})"

class Wallet(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wallets')
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    balance = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    locked = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'currency')

    def __str__(self):
        return f"{self.user.username}'s {self.currency.code} Wallet"

class Transaction(models.Model):
    TRANSACTION_TYPES = (
        ('deposit', 'Deposit'),
        ('withdrawal', 'Withdrawal'),
        ('transfer', 'Transfer'),
        ('trade', 'Trade'),
        ('staking', 'Staking'),
        ('earning', 'Earning'),
    )
    
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('canceled', 'Canceled'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=20, decimal_places=8, validators=[MinValueValidator(0)])
    fee = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    address = models.CharField(max_length=255, blank=True, null=True)
    txid = models.CharField(max_length=255, blank=True, null=True)
    memo = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_type_display()} - {self.amount} {self.currency.code} ({self.status})"

class DepositAddress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='deposit_addresses')
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    address = models.CharField(max_length=255)
    memo = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'currency', 'address', 'memo')

    def __str__(self):
        return f"{self.user.username}'s {self.currency.code} Deposit Address"

class WithdrawalLimit(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='withdrawal_limits')
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE)
    limit_24h = models.DecimalField(max_digits=20, decimal_places=8)
    used_24h = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'currency')

    def __str__(self):
        return f"{self.user.username}'s {self.currency.code} Withdrawal Limit"

class ExchangeRate(models.Model):
    base_currency = models.ForeignKey(Currency, on_delete=models.CASCADE, related_name='base_rates')
    quote_currency = models.ForeignKey(Currency, on_delete=models.CASCADE, related_name='quote_rates')
    rate = models.DecimalField(max_digits=20, decimal_places=8)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('base_currency', 'quote_currency')

    def __str__(self):
        return f"1 {self.base_currency.code} = {self.rate} {self.quote_currency.code}"