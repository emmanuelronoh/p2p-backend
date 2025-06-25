import uuid
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.conf import settings
from decimal import Decimal


class P2PListing(models.Model):
    PAYMENT_METHODS = (
        (1, 'Cash'),
        (2, 'Hawala'),
        (3, 'Other'),
    )

    STATUS_CHOICES = (
        (1, 'Active'),
        (2, 'Funded'),
        (3, 'Reserved'),
        (4, 'Completed'),
        (5, 'Expired'),
    )

    CRYPTO_TYPES = (
        ('buy', 'Buy'),
        ('sell', 'Sell'),
    )

    escrow_wallet = models.ForeignKey(
        'escrow.EscrowWallet',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller_token = models.CharField(max_length=64, help_text="HMAC-SHA256(seller_identity)")

    crypto_type = models.CharField(max_length=10, choices=CRYPTO_TYPES)
    crypto_currency = models.CharField(max_length=10, default='USDT')
    crypto_amount = models.DecimalField(max_digits=20, decimal_places=6, validators=[MinValueValidator(0)])

    fiat_currency = models.CharField(max_length=10, default='USD')
    usdt_amount = models.DecimalField(max_digits=20, decimal_places=2, validators=[MinValueValidator(0)])

    payment_method = models.SmallIntegerField(choices=PAYMENT_METHODS, help_text="1=Cash,2=Hawala,3=Other")
    description = models.TextField(blank=True, null=True)

    instructions_enc = models.TextField(null=True, blank=True, help_text="Encrypted with session key")

    status = models.SmallIntegerField(choices=STATUS_CHOICES, default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=['seller_token'], name='idx_listing_seller'),
            models.Index(fields=['status'], name='idx_listing_status'),
            models.Index(fields=['payment_method'], name='idx_listing_payment_type'),
            models.Index(fields=['expires_at'], name='idx_listing_expiry'),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"Listing {self.id} - {self.get_status_display()}"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(
                days=settings.XUSDT_SETTINGS['LISTING_EXPIRY_DAYS']
            )
        super().save(*args, **kwargs)

class P2PTrade(models.Model):
    STATUS_CHOICES = (
        (0, 'Created'),
        (1, 'Funded'),  # Fixed typo from 'Funded' to 'Funded'
        (2, 'PaymentSent'),
        (3, 'Completed'),
        (4, 'Disputed'),
        (5, 'Canceled'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    listing = models.ForeignKey(
        P2PListing,
        on_delete=models.RESTRICT,
        related_name='trades'
    )
    buyer_token = models.CharField(max_length=64)
    seller_token = models.CharField(max_length=64)
    escrow_tx_hash = models.CharField(max_length=66)
    usdt_amount = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=0.00  
    )
    payment_proof_hash = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text="SHA3-256(payment_details)"
    )
    status = models.SmallIntegerField(
        choices=STATUS_CHOICES,
        default=0,
        help_text="0=Created,1=Funded,2=PaymentSent,3=Completed,4=Disputed,5=Canceled"
    )
    fee_amount = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        default=0.0025,
        help_text="0.25% platform fee"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['listing'], name='idx_trade_listing'),
            models.Index(fields=['buyer_token'], name='idx_trade_buyer'),
            models.Index(fields=['seller_token'], name='idx_trade_seller'),
            models.Index(fields=['status'], name='idx_trade_status'),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"Trade {self.id} - {self.get_status_display()}"

    def calculate_fee(self):
        """Calculate platform fee based on trade amount"""
        from decimal import Decimal
        try:
            fee_percent = Decimal(str(settings.XUSDT_SETTINGS['ESCROW_FEE_PERCENT'])) / Decimal(100)
            calculated_fee = self.listing.usdt_amount * fee_percent
            min_fee = Decimal(str(settings.XUSDT_SETTINGS['ESCROW_MIN_FEE']))
            self.fee_amount = max(calculated_fee, min_fee)
            return self.fee_amount
        except (TypeError, ValueError, KeyError) as e:
            # Handle error appropriately - maybe log it and return a default fee
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error calculating fee: {str(e)}")
            return Decimal('0')