from rest_framework import serializers
from django.conf import settings
from .models import P2PListing, P2PTrade
import hmac
import hashlib


class P2PListingSerializer(serializers.ModelSerializer):
    is_owner = serializers.SerializerMethodField()
    
    class Meta:
        model = P2PListing
        fields = [
            'id',
            'is_owner',  # Added instead of exposing raw token
            'crypto_type',
            'crypto_currency',
            'crypto_amount',
            'fiat_currency',
            'usdt_amount',
            'payment_method',
            'description',
            'status',
            'created_at',
            'expires_at'
        ]
        read_only_fields = [
            'id',
            'is_owner',
            'status',
            'created_at',
            'expires_at'
        ]
        extra_kwargs = {
            'crypto_type': {'required': True},
            'crypto_currency': {'required': True},
            'crypto_amount': {
                'required': True,
                'min_value': 0.000001  # Minimum USDT amount (6 decimals)
            },
            'fiat_currency': {'required': True},
            'usdt_amount': {
                'required': True,
                'min_value': 0.01  # Minimum $0.01
            },
            'payment_method': {'required': True},
        }

    def get_is_owner(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            client_token = request.user.client_token
            hmac_key = settings.XUSDT_SETTINGS["USER_TOKEN_HMAC_KEY"].encode()
            user_token = hmac.new(hmac_key, client_token.encode(), hashlib.sha256).hexdigest()
            return user_token == obj.seller_token
        return False


class P2PTradeCreateSerializer(serializers.ModelSerializer):
    listing = serializers.PrimaryKeyRelatedField(
        queryset=P2PListing.objects.filter(status=1),
        help_text="UUID of the listing being traded"
    )

    class Meta:
        model = P2PTrade
        fields = ['id', 'listing', 'escrow_tx_hash', 'payment_proof_hash']
        extra_kwargs = {
            'escrow_tx_hash': {'required': True},
            'payment_proof_hash': {'required': False}  # Might be added later
        }


class P2PTradeSerializer(serializers.ModelSerializer):
    listing = P2PListingSerializer(read_only=True)
    role = serializers.SerializerMethodField()
    
    class Meta:
        model = P2PTrade
        fields = [
            'id',
            'listing',
            'escrow_tx_hash',
            'payment_proof_hash',
            'status',
            'fee_amount',
            'created_at',
            'updated_at',
            'completed_at',
            'role'  # Removed direct token exposure
        ]
        read_only_fields = fields

    def get_role(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            client_token = request.user.client_token
            hmac_key = settings.XUSDT_SETTINGS["USER_TOKEN_HMAC_KEY"].encode()
            user_token = hmac.new(hmac_key, client_token.encode(), hashlib.sha256).hexdigest()
            
            if user_token == obj.buyer_token:
                return 'buyer'
            elif user_token == obj.seller_token:
                return 'seller'
        return 'unknown'