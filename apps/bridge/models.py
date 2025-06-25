from django.db import models
from django.utils import timezone
from uuid import uuid4
from django.core.validators import MinValueValidator
from decimal import Decimal

class BridgeNetwork(models.Model):
    """
    Supported networks for bridging
    """
    name = models.CharField(max_length=100)
    chain_id = models.PositiveIntegerField(unique=True)
    is_evm = models.BooleanField(default=True)
    native_token_symbol = models.CharField(max_length=20)
    rpc_url = models.URLField()
    explorer_url = models.URLField()
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.name

class BridgeToken(models.Model):
    """
    Supported tokens for bridging
    """
    symbol = models.CharField(max_length=20)
    name = models.CharField(max_length=100)
    contract_address = models.CharField(max_length=42, blank=True, null=True)
    decimals = models.PositiveSmallIntegerField(default=18)
    is_active = models.BooleanField(default=True)
    
    # Networks where this token is available
    networks = models.ManyToManyField(BridgeNetwork, through='BridgeTokenNetwork')
    
    def __str__(self):
        return f"{self.symbol} ({self.name})"

class BridgeTokenNetwork(models.Model):
    """
    Junction table for tokens and networks with network-specific data
    """
    token = models.ForeignKey(BridgeToken, on_delete=models.CASCADE)
    network = models.ForeignKey(BridgeNetwork, on_delete=models.CASCADE)
    contract_address = models.CharField(max_length=42)
    min_bridge_amount = models.DecimalField(max_digits=30, decimal_places=18, default=Decimal('0'))
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ('token', 'network')
    
    def __str__(self):
        return f"{self.token.symbol} on {self.network.name}"

class BridgeQuote(models.Model):
    """
    Bridge quotes
    """
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    token = models.ForeignKey(BridgeToken, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=30, decimal_places=18, validators=[MinValueValidator(0)])
    from_network = models.ForeignKey(BridgeNetwork, on_delete=models.CASCADE, related_name='quotes_from')
    to_network = models.ForeignKey(BridgeNetwork, on_delete=models.CASCADE, related_name='quotes_to')
    fee_amount = models.DecimalField(max_digits=30, decimal_places=18, validators=[MinValueValidator(0)])
    estimated_time = models.PositiveIntegerField(help_text="Estimated time in minutes")
    valid_until = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Bridge {self.token.symbol} {self.amount} {self.from_network}→{self.to_network}"

class BridgeTransaction(models.Model):
    """
    Bridge transactions
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    user_token = models.CharField(max_length=64)  # HMAC-SHA256(user_identity)
    quote = models.ForeignKey(BridgeQuote, on_delete=models.PROTECT)
    from_address = models.CharField(max_length=42)
    to_address = models.CharField(max_length=42)
    deposit_tx_hash = models.CharField(max_length=66, blank=True, null=True)
    receive_tx_hash = models.CharField(max_length=66, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    initiated_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['user_token']),
            models.Index(fields=['status']),
            models.Index(fields=['deposit_tx_hash']),
            models.Index(fields=['receive_tx_hash']),
        ]
    
    def __str__(self):
        return f"Bridge {self.id} ({self.status})"

class BridgeFee(models.Model):
    """
    Bridge fees structure
    """
    from_network = models.ForeignKey(BridgeNetwork, on_delete=models.CASCADE, related_name='fees_from')
    to_network = models.ForeignKey(BridgeNetwork, on_delete=models.CASCADE, related_name='fees_to')
    token = models.ForeignKey(BridgeToken, on_delete=models.CASCADE)
    fee_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    is_active = models.BooleanField(default=True)
    min_fee = models.DecimalField(max_digits=30, decimal_places=18)
    max_fee = models.DecimalField(max_digits=30, decimal_places=18)
    
    class Meta:
        unique_together = ('from_network', 'to_network', 'token')
    
    def __str__(self):
        return f"Fee {self.token.symbol} {self.from_network}→{self.to_network}"

class BridgeStats(models.Model):
    """
    Bridge statistics
    """
    network_pair = models.CharField(max_length=100)  # e.g., "Ethereum-BSC"
    total_volume = models.DecimalField(max_digits=30, decimal_places=18)
    total_transactions = models.PositiveIntegerField()
    avg_completion_time = models.PositiveIntegerField(help_text="Average completion time in minutes")
    last_updated = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.network_pair} stats"