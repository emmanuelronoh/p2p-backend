from django.db import models
from django.utils import timezone
from uuid import uuid4
from django.core.validators import MinValueValidator
from decimal import Decimal

class SwapToken(models.Model):
    """
    Supported tokens for swapping
    """
    symbol = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    contract_address = models.CharField(max_length=42, blank=True, null=True)
    decimals = models.PositiveSmallIntegerField(default=18)
    is_active = models.BooleanField(default=True)
    logo_url = models.URLField(blank=True, null=True)
    network = models.CharField(max_length=50)  # e.g., Ethereum, BSC, Polygon
    min_swap_amount = models.DecimalField(max_digits=30, decimal_places=18, default=Decimal('0'))
    
    def __str__(self):
        return f"{self.symbol} ({self.network})"

class SwapRoute(models.Model):
    """
    Available swap routes between tokens
    """
    token_in = models.ForeignKey(SwapToken, on_delete=models.CASCADE, related_name='routes_in')
    token_out = models.ForeignKey(SwapToken, on_delete=models.CASCADE, related_name='routes_out')
    is_active = models.BooleanField(default=True)
    fee_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.3'))
    min_amount_in = models.DecimalField(max_digits=30, decimal_places=18)
    max_amount_in = models.DecimalField(max_digits=30, decimal_places=18)
    
    class Meta:
        unique_together = ('token_in', 'token_out')
    
    def __str__(self):
        return f"{self.token_in.symbol} → {self.token_out.symbol}"

class SwapQuote(models.Model):
    """
    Stored swap quotes
    """
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    token_in = models.ForeignKey(SwapToken, on_delete=models.CASCADE, related_name='quotes_in')
    token_out = models.ForeignKey(SwapToken, on_delete=models.CASCADE, related_name='quotes_out')
    amount_in = models.DecimalField(max_digits=30, decimal_places=18, validators=[MinValueValidator(0)])
    amount_out = models.DecimalField(max_digits=30, decimal_places=18, validators=[MinValueValidator(0)])
    rate = models.DecimalField(max_digits=30, decimal_places=18, validators=[MinValueValidator(0)])
    fee_amount = models.DecimalField(max_digits=30, decimal_places=18, validators=[MinValueValidator(0)])
    valid_until = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Quote {self.id}: {self.amount_in} {self.token_in.symbol} → {self.amount_out} {self.token_out.symbol}"

class SwapTransaction(models.Model):
    """
    Swap execution records
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    user_token = models.CharField(max_length=64)  # HMAC-SHA256(user_identity)
    quote = models.ForeignKey(SwapQuote, on_delete=models.PROTECT)
    tx_hash = models.CharField(max_length=66, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    from_address = models.CharField(max_length=42)
    to_address = models.CharField(max_length=42)
    executed_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['user_token']),
            models.Index(fields=['status']),
            models.Index(fields=['tx_hash']),
        ]
    
    def __str__(self):
        return f"Swap {self.id} ({self.status})"

class SwapAllowance(models.Model):
    """
    Token allowances for swap contracts
    """
    user_token = models.CharField(max_length=64)
    token = models.ForeignKey(SwapToken, on_delete=models.CASCADE)
    contract_address = models.CharField(max_length=42)
    allowance_amount = models.DecimalField(max_digits=30, decimal_places=18, default=Decimal('0'))
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('user_token', 'token', 'contract_address')
    
    def __str__(self):
        return f"Allowance for {self.token.symbol} by {self.user_token[:8]}..."

class SwapPrice(models.Model):
    """
    Historical price data for tokens
    """
    token = models.ForeignKey(SwapToken, on_delete=models.CASCADE)
    price_usd = models.DecimalField(max_digits=30, decimal_places=18)
    timestamp = models.DateTimeField(default=timezone.now)
    
    class Meta:
        indexes = [
            models.Index(fields=['token', '-timestamp']),
        ]
    
    def __str__(self):
        return f"{self.token.symbol} @ ${self.price_usd}"

class MarketStats(models.Model):
    """
    Market statistics for swap pairs
    """
    token_pair = models.CharField(max_length=20)  # e.g., "ETH_USDT"
    volume_24h = models.DecimalField(max_digits=30, decimal_places=18)
    high_24h = models.DecimalField(max_digits=30, decimal_places=18)
    low_24h = models.DecimalField(max_digits=30, decimal_places=18)
    change_24h = models.DecimalField(max_digits=10, decimal_places=2)
    last_updated = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.token_pair} stats"