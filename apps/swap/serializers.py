from rest_framework import serializers
from .models import (
    SwapToken, SwapRoute, SwapQuote,
    SwapTransaction, SwapAllowance,
    SwapPrice, MarketStats
)
from django.utils import timezone
from decimal import Decimal

class TokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = SwapToken
        fields = [
            'symbol', 'name', 'contract_address',
            'decimals', 'is_active', 'logo_url',
            'network', 'min_swap_amount'
        ]
        read_only_fields = ['symbol', 'name', 'decimals']

class RouteSerializer(serializers.ModelSerializer):
    token_in = TokenSerializer()
    token_out = TokenSerializer()
    
    class Meta:
        model = SwapRoute
        fields = [
            'id', 'token_in', 'token_out',
            'is_active', 'fee_percentage',
            'min_amount_in', 'max_amount_in'
        ]

class QuoteSerializer(serializers.ModelSerializer):
    token_in = TokenSerializer()
    token_out = TokenSerializer()
    valid_until = serializers.SerializerMethodField()
    
    class Meta:
        model = SwapQuote
        fields = [
            'id', 'token_in', 'token_out',
            'amount_in', 'amount_out', 'rate',
            'fee_amount', 'valid_until'
        ]
    
    def get_valid_until(self, obj):
        return obj.valid_until.timestamp()

class TransactionSerializer(serializers.ModelSerializer):
    quote = QuoteSerializer()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    execution_time = serializers.SerializerMethodField()
    
    class Meta:
        model = SwapTransaction
        fields = [
            'id', 'quote', 'tx_hash', 'status',
            'status_display', 'from_address',
            'to_address', 'executed_at',
            'completed_at', 'created_at',
            'execution_time'
        ]
        read_only_fields = fields
    
    def get_execution_time(self, obj):
        if obj.executed_at and obj.completed_at:
            return (obj.completed_at - obj.executed_at).total_seconds()
        return None

class AllowanceSerializer(serializers.ModelSerializer):
    token = TokenSerializer()
    last_updated = serializers.SerializerMethodField()
    
    class Meta:
        model = SwapAllowance
        fields = [
            'token', 'contract_address',
            'allowance_amount', 'last_updated'
        ]
    
    def get_last_updated(self, obj):
        return obj.last_updated.timestamp()

class PriceSerializer(serializers.ModelSerializer):
    token = TokenSerializer()
    timestamp = serializers.SerializerMethodField()
    
    class Meta:
        model = SwapPrice
        fields = ['token', 'price_usd', 'timestamp']
    
    def get_timestamp(self, obj):
        return obj.timestamp.timestamp()

class MarketStatsSerializer(serializers.ModelSerializer):
    last_updated = serializers.SerializerMethodField()
    
    class Meta:
        model = MarketStats
        fields = [
            'token_pair', 'volume_24h',
            'high_24h', 'low_24h',
            'change_24h', 'last_updated'
        ]
    
    def get_last_updated(self, obj):
        return obj.last_updated.timestamp()

class SwapQuoteRequestSerializer(serializers.Serializer):
    token_in = serializers.CharField(max_length=20)
    token_out = serializers.CharField(max_length=20)
    amount_in = serializers.DecimalField(max_digits=30, decimal_places=18)
    
    def validate_amount_in(self, value):
        if value <= Decimal('0'):
            raise serializers.ValidationError("Amount must be positive")
        return value

class SwapExecuteRequestSerializer(serializers.Serializer):
    quote_id = serializers.UUIDField()
    from_address = serializers.CharField(max_length=42)
    to_address = serializers.CharField(max_length=42)
    
    def validate_from_address(self, value):
        if not value.startswith('0x') or len(value) != 42:
            raise serializers.ValidationError("Invalid Ethereum address")
        return value.lower()
    
    def validate_to_address(self, value):
        if not value.startswith('0x') or len(value) != 42:
            raise serializers.ValidationError("Invalid Ethereum address")
        return value.lower()

class AllowanceRequestSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=20)
    contract_address = serializers.CharField(max_length=42)
    amount = serializers.DecimalField(max_digits=30, decimal_places=18)
    
    def validate_contract_address(self, value):
        if not value.startswith('0x') or len(value) != 42:
            raise serializers.ValidationError("Invalid contract address")
        return value.lower()