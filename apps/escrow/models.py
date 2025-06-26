import uuid
import hmac
import hashlib
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinLengthValidator
from .validators import validate_eth_address

class EscrowWallet(models.Model):
    STATUS_CREATED = 'created'
    STATUS_FUNDED = 'funded'
    STATUS_RELEASED = 'released'
    STATUS_DISPUTED = 'disputed'
    
    STATUS_CHOICES = [
        (STATUS_CREATED, 'Created'),
        (STATUS_FUNDED, 'Funded'),
        (STATUS_RELEASED, 'Released'),
        (STATUS_DISPUTED, 'Disputed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    address = models.CharField(
        max_length=42,
        unique=True,
        help_text="ETH address"
    )
    user_token = models.CharField(
        max_length=64,
        help_text="HMAC-SHA256(user_identity)"
    )
    balance_commitment = models.CharField(
        max_length=64,
        help_text="SHA3-256(balance+salt)"
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_CREATED,
        help_text="Current status of the escrow"
    )

    buyer_address = models.CharField(
        max_length=42,
        blank=True,
        null=True,
        validators=[validate_eth_address],
        help_text="ETH address of the buyer"
    )
    seller_address = models.CharField(
        max_length=42,
        blank=True,
        null=True,
        validators=[validate_eth_address],
        help_text="ETH address of the seller"
    )
    amount = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        blank=True,
        null=True,
        help_text="Amount in USDT"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['address'], name='idx_escrow_address'),
            models.Index(fields=['user_token'], name='idx_escrow_user'),
            models.Index(fields=['status'], name='idx_escrow_status'),
        ]

    def __str__(self):
        return f"Escrow {self.address} (Status: {self.get_status_display()})"

    @classmethod
    def generate_user_token(cls, client_token):
        """Generate HMAC-SHA256 user token from client token"""
        hmac_key = settings.XUSDT_SETTINGS['USER_TOKEN_HMAC_KEY'].encode()
        return hmac.new(hmac_key, client_token.encode(), hashlib.sha256).hexdigest()

    def mark_as_funded(self, amount):
        """Mark escrow as funded with the given amount"""
        self.status = self.STATUS_FUNDED
        self.amount = amount
        self.save(update_fields=['status', 'amount', 'last_used'])

    def mark_as_released(self):
        """Mark escrow as released"""
        self.status = self.STATUS_RELEASED
        self.save(update_fields=['status', 'last_used'])

    def mark_as_disputed(self):
        """Mark escrow as disputed"""
        self.status = self.STATUS_DISPUTED
        self.save(update_fields=['status', 'last_used'])


class TransactionQueue(models.Model):
    PENDING = 1
    PROCESSING = 2
    COMPLETED = 3
    FAILED = 4
    
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (PROCESSING, 'Processing'),
        (COMPLETED, 'Completed'),
        (FAILED, 'Failed'),
    ]
    
    tx_hash = models.CharField(max_length=66)
    tx_type = models.CharField(max_length=50)
    status = models.IntegerField(choices=STATUS_CHOICES, default=PENDING)
    retry_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['status'], name='idx_txqueue_status'),
            models.Index(fields=['tx_hash'], name='idx_txqueue_hash'),
        ]
        
class EscrowDispute(models.Model):
    OPEN = 1
    IN_REVIEW = 2
    RESOLVED = 3
    
    STATUS_CHOICES = [
        (OPEN, 'Open'),
        (IN_REVIEW, 'In Review'),
        (RESOLVED, 'Resolved'),
    ]
    
    escrow = models.ForeignKey(
        EscrowWallet, 
        on_delete=models.CASCADE, 
        related_name='disputes'
    )
    initiator = models.CharField(max_length=64)  # user_token
    reason = models.TextField()
    status = models.IntegerField(
        choices=STATUS_CHOICES,
        default=OPEN
    )
    resolution = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['status'], name='idx_dispute_status'),
        ]

    def __str__(self):
        return f"Dispute #{self.id} ({self.get_status_display()})"


class SystemWallet(models.Model):
    address = models.CharField(
        max_length=42,
        primary_key=True,
        help_text="ETH address"
    )
    private_key_enc = models.TextField(
        help_text="Age-encrypted private key"
    )
    current_balance = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        default=0
    )
    collected_fees = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        default=0
    )
    last_swept_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['current_balance'], name='idx_wallet_balance'),
        ]

    def __str__(self):
        return f"System Wallet {self.address}"
    

class EscrowAuditLog(models.Model):
    ACTION_CHOICES = [
        ('CREATE', 'Create'),
        ('FUND', 'Fund'),
        ('RELEASE', 'Release'),
        ('DISPUTE', 'Dispute'),
    ]
    
    escrow = models.ForeignKey(EscrowWallet, on_delete=models.CASCADE, related_name='audit_logs')
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    details = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']