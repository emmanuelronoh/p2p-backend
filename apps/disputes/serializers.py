from rest_framework import serializers
from .models import TradeDispute
import json
import re
# In serializers.py
class TradeDisputeSerializer(serializers.ModelSerializer):
    trade_id = serializers.UUIDField(source='trade.id', read_only=True)
    status = serializers.CharField(source='get_resolution_display', read_only=True)
    
    class Meta:
        model = TradeDispute
        fields = [
            'id', 'trade_id', 'status', 'initiator_token', 
            'evidence_hashes', 'evidence_ipfs_cid',
            'resolution', 'admin_sig', 'created_at', 'resolved_at'
        ]
        read_only_fields = ['id', 'created_at', 'resolved_at', 'admin_sig']
        
    def validate_evidence_hashes(self, value):
        if value:
            try:
                hashes = json.loads(value)
                if not isinstance(hashes, list):
                    raise serializers.ValidationError("Evidence hashes must be a JSON array")
                for h in hashes:
                    if not re.match(r'^[a-f0-9]{64}$', h):
                        raise serializers.ValidationError("Invalid SHA3-256 hash format")
            except json.JSONDecodeError:
                raise serializers.ValidationError("Invalid JSON format for evidence hashes")
        return value