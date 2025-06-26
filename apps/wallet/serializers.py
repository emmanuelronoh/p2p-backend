from rest_framework import serializers
from .models import (
    Currency, Wallet, Transaction, 
    DepositAddress, WithdrawalLimit, ExchangeRate,
    NetworkFee, UserAddressBook
)
from rest_framework.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
import uuid

class CurrencySerializer(serializers.ModelSerializer):
    network = serializers.CharField(source='get_network_display')
    withdrawal_fee_type = serializers.CharField(source='get_withdrawal_fee_type_display')
    type = serializers.CharField(source='get_type_display')

    class Meta:
        model = Currency
        fields = [
            'code', 'name', 'type', 'network', 'is_active',
            'min_withdrawal', 'min_deposit', 'withdrawal_fee',
            'withdrawal_fee_type', 'deposit_enabled', 'withdrawal_enabled',
            'trading_enabled', 'precision', 'confirmations_required',
            'contract_address', 'icon_url', 'created_at'
        ]
        read_only_fields = ['code', 'created_at']

class WalletSerializer(serializers.ModelSerializer):
    currency = CurrencySerializer()
    available = serializers.DecimalField(max_digits=20, decimal_places=8, read_only=True)
    staked = serializers.DecimalField(max_digits=20, decimal_places=8, read_only=True)
    interest_owed = serializers.DecimalField(max_digits=20, decimal_places=8, read_only=True)

    class Meta:
        model = Wallet
        fields = [
            'id', 'currency', 'balance', 'locked', 'available',
            'staked', 'interest_owed', 'address', 'updated_at'
        ]
        read_only_fields = ['id', 'address', 'updated_at']

class TransactionSerializer(serializers.ModelSerializer):
    currency = CurrencySerializer()
    wallet = WalletSerializer()
    status = serializers.CharField(source='get_status_display')
    type = serializers.CharField(source='get_type_display')
    fee_currency = CurrencySerializer()

    class Meta:
        model = Transaction
        fields = [
            'id', 'wallet', 'currency', 'amount', 'fee', 'fee_currency',
            'type', 'status', 'address', 'memo', 'txid', 'confirmations',
            'required_confirmations', 'network', 'from_address', 'to_address',
            'description', 'metadata', 'created_at', 'updated_at', 'completed_at'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'completed_at', 'confirmations',
            'txid', 'status', 'fee', 'fee_currency'
        ]

class CreateTransactionSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    network = serializers.CharField(required=False)
    memo = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Transaction
        fields = ['id', 'currency', 'amount', 'type', 'address', 'memo', 'network']
        extra_kwargs = {
            'address': {'required': True},
        }

    def validate(self, data):
        request = self.context.get('request')
        user = request.user if request else None
        
        if data['type'] == 'withdrawal':
            # Check wallet balance
            wallet = Wallet.objects.get(
                user=user,
                currency=data['currency']
            )
            
            if wallet.available_balance < data['amount']:
                raise ValidationError("Insufficient available balance")
            
            # Check withdrawal limits
            limit = WithdrawalLimit.objects.filter(
                user=user,
                currency=data['currency'],
                reset_at__gte=timezone.now()
            ).first()
            
            if limit and (limit.used_amount + data['amount']) > limit.limit_amount:
                raise ValidationError("Withdrawal limit exceeded")
            
            # Validate address format based on currency
            if not self._validate_address(data['currency'], data['address']):
                raise ValidationError("Invalid address format for this currency")
            
        elif data['type'] == 'deposit':
            raise ValidationError("Deposits must be processed through blockchain transactions")
        
        return data

    def _validate_address(self, currency, address):
        """Basic address validation - should be enhanced with currency-specific validation"""
        # In production, implement proper address validation for each currency
        return len(address) >= 20  # Simple length check

class DepositAddressSerializer(serializers.ModelSerializer):
    currency = CurrencySerializer()
    qr_code_url = serializers.SerializerMethodField()

    class Meta:
        model = DepositAddress
        fields = [
            'id', 'currency', 'address', 'memo', 'qr_code_url',
            'is_active', 'label', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_qr_code_url(self, obj):
        # Generate QR code URL for the address
        base_url = self.context.get('request').build_absolute_uri('/')
        return f"{base_url}qr/{obj.address}"

class CreateDepositAddressSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    label = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = DepositAddress
        fields = ['id', 'currency', 'label']

    def validate(self, data):
        user = self.context.get('request').user
        currency = data['currency']
        
        if not currency.deposit_enabled:
            raise ValidationError("Deposits are currently disabled for this currency")
        
        # Limit number of active deposit addresses
        active_addresses = DepositAddress.objects.filter(
            user=user,
            currency=currency,
            is_active=True
        ).count()
        
        if active_addresses >= 5:  # Configurable limit
            raise ValidationError("Maximum number of active deposit addresses reached")
        
        return data

class WithdrawalLimitSerializer(serializers.ModelSerializer):
    currency = CurrencySerializer()
    period = serializers.CharField(source='get_period_display')
    tier = serializers.CharField(source='get_tier_display')
    remaining_amount = serializers.DecimalField(max_digits=20, decimal_places=8, read_only=True)
    reset_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = WithdrawalLimit
        fields = [
            'currency', 'period', 'tier', 'limit_amount',
            'used_amount', 'remaining_amount', 'reset_at', 'updated_at'
        ]
        read_only_fields = ['updated_at']

class ExchangeRateSerializer(serializers.ModelSerializer):
    base_currency = CurrencySerializer()
    quote_currency = CurrencySerializer()
    rate_type = serializers.CharField(source='get_rate_type_display')

    class Meta:
        model = ExchangeRate
        fields = [
            'base_currency', 'quote_currency', 'rate', 'rate_type',
            'source', 'updated_at', 'valid_until'
        ]
        read_only_fields = ['updated_at']

class NetworkFeeSerializer(serializers.ModelSerializer):
    currency = CurrencySerializer()

    class Meta:
        model = NetworkFee
        fields = [
            'currency', 'network', 'withdrawal_fee', 'withdrawal_min',
            'deposit_enabled', 'withdrawal_enabled', 'updated_at'
        ]
        read_only_fields = ['updated_at']

class UserAddressBookSerializer(serializers.ModelSerializer):
    currency = CurrencySerializer()
    address_type = serializers.CharField(source='get_address_type_display')

    class Meta:
        model = UserAddressBook
        fields = [
            'id', 'currency', 'address', 'memo', 'address_type',
            'label', 'is_verified', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def validate(self, data):
        # Validate address format based on currency
        currency = data['currency']
        address = data['address']
        
        if not self._validate_address(currency, address):
            raise ValidationError("Invalid address format for this currency")
        
        return data

    def _validate_address(self, currency, address):
        """Basic address validation - should be enhanced with currency-specific validation"""
        # In production, implement proper address validation for each currency
        return len(address) >= 20  # Simple length check

class PortfolioSummarySerializer(serializers.Serializer):
    total_balance = serializers.DecimalField(max_digits=20, decimal_places=8)
    total_balance_btc = serializers.DecimalField(max_digits=20, decimal_places=8)
    total_balance_usd = serializers.DecimalField(max_digits=20, decimal_places=2)
    currencies = serializers.ListField(child=serializers.DictField())
    last_updated = serializers.DateTimeField()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['currencies'] = sorted(
            data['currencies'],
            key=lambda x: x['usd_value'],
            reverse=True
        )
        return data

class TransactionHistorySerializer(serializers.Serializer):
    transactions = TransactionSerializer(many=True)
    total_count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()