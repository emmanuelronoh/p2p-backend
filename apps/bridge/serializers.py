from rest_framework import serializers
from .models import (
    BridgeNetwork, BridgeToken, BridgeTokenNetwork,
    BridgeQuote, BridgeTransaction, BridgeFee, BridgeStats
)
from django.utils import timezone
from decimal import Decimal

class NetworkSerializer(serializers.ModelSerializer):
    class Meta:
        model = BridgeNetwork
        fields = [
            'id', 'name', 'chain_id',
            'native_token_symbol', 'rpc_url',
            'explorer_url', 'is_active'
        ]
        read_only_fields = ['chain_id', 'native_token_symbol']

class TokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = BridgeToken
        fields = [
            'id', 'symbol', 'name',
            'contract_address', 'decimals',
            'is_active'
        ]
        read_only_fields = ['symbol', 'name', 'decimals']

class TokenNetworkSerializer(serializers.ModelSerializer):
    token = TokenSerializer()
    network = NetworkSerializer()
    
    class Meta:
        model = BridgeTokenNetwork
        fields = [
            'id', 'token', 'network',
            'contract_address', 'min_bridge_amount',
            'is_active'
        ]

class QuoteSerializer(serializers.ModelSerializer):
    token = TokenSerializer()
    from_network = NetworkSerializer()
    to_network = NetworkSerializer()
    valid_until = serializers.SerializerMethodField()
    
    class Meta:
        model = BridgeQuote
        fields = [
            'id', 'token', 'amount',
            'from_network', 'to_network',
            'fee_amount', 'estimated_time',
            'valid_until'
        ]
    
    def get_valid_until(self, obj):
        return obj.valid_until.timestamp()

class TransactionSerializer(serializers.ModelSerializer):
    quote = QuoteSerializer()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    completion_time = serializers.SerializerMethodField()
    
    class Meta:
        model = BridgeTransaction
        fields = [
            'id', 'quote', 'from_address',
            'to_address', 'deposit_tx_hash',
            'receive_tx_hash', 'status',
            'status_display', 'initiated_at',
            'completed_at', 'completion_time'
        ]
        read_only_fields = fields
    
    def get_completion_time(self, obj):
        if obj.initiated_at and obj.completed_at:
            return (obj.completed_at - obj.initiated_at).total_seconds()
        return None

class FeeSerializer(serializers.ModelSerializer):
    from_network = NetworkSerializer()
    to_network = NetworkSerializer()
    token = TokenSerializer()
    
    class Meta:
        model = BridgeFee
        fields = [
            'from_network', 'to_network',
            'token', 'fee_percentage',
            'min_fee', 'max_fee'
        ]

class StatsSerializer(serializers.ModelSerializer):
    last_updated = serializers.SerializerMethodField()
    
    class Meta:
        model = BridgeStats
        fields = [
            'network_pair', 'total_volume',
            'total_transactions', 'avg_completion_time',
            'last_updated'
        ]
    
    def get_last_updated(self, obj):
        return obj.last_updated.timestamp()

class QuoteRequestSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=20)
    amount = serializers.DecimalField(max_digits=30, decimal_places=18)
    from_network = serializers.IntegerField()
    to_network = serializers.IntegerField()
    
    def validate_amount(self, value):
        if value <= Decimal('0'):
            raise serializers.ValidationError("Amount must be positive")
        return value

class InitiateBridgeRequestSerializer(serializers.Serializer):
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