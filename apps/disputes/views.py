from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
import hmac
import hashlib
import json

from .models import TradeDispute
from .serializers import TradeDisputeSerializer


class TradeDisputeCreateView(generics.CreateAPIView):
    """Create a new dispute for a trade.

    * Only one dispute per trade is allowed.
    * Evidence hashes (if provided) must be a JSON list.
    * The initiator token is derived from the user's client token using HMAC‑SHA256.
    """

    queryset = TradeDispute.objects.all()
    serializer_class = TradeDisputeSerializer
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "disputes"

    def create(self, request, *args, **kwargs):
        trade_id = request.data.get("trade")
        if not trade_id:
            raise ValidationError({"trade": "This field is required."})

        if TradeDispute.objects.filter(trade_id=trade_id).exists():
            return Response(
                {"detail": "Dispute already exists for this trade"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        client_token = self.request.user.client_token
        hmac_key = settings.XUSDT_SETTINGS["USER_TOKEN_HMAC_KEY"].encode()
        initiator_token = hmac.new(hmac_key, client_token.encode(), hashlib.sha256).hexdigest()

        # Validate evidence_hashes if provided
        evidence_hashes = serializer.validated_data.get("evidence_hashes")
        if evidence_hashes:
            try:
                hashes = json.loads(evidence_hashes)
            except json.JSONDecodeError:
                raise ValidationError({"evidence_hashes": "Invalid JSON format"})

            if not isinstance(hashes, list):
                raise ValidationError({"evidence_hashes": "Must be a JSON array"})

        serializer.save(initiator_token=initiator_token)


class TradeDisputeDetailView(generics.RetrieveUpdateAPIView):
    """Retrieve a single dispute or update evidence / resolution status."""

    serializer_class = TradeDisputeSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "pk"
    lookup_url_kwarg = "pk"

    def get_queryset(self):
        client_token = self.request.user.client_token
        hmac_key = settings.XUSDT_SETTINGS["USER_TOKEN_HMAC_KEY"].encode()
        user_token = hmac.new(hmac_key, client_token.encode(), hashlib.sha256).hexdigest()

        return TradeDispute.objects.filter(
            Q(trade__buyer_token=user_token)
            | Q(trade__seller_token=user_token)
            | Q(initiator_token=user_token)
        )

    def perform_update(self, serializer):
        instance = self.get_object()

        # Non‑staff users may only update evidence fields
        allowed_fields = {"evidence_hashes", "evidence_ipfs_cid"}
        if not self.request.user.is_staff:
            illegal_fields = set(serializer.validated_data) - allowed_fields
            if illegal_fields:
                raise PermissionDenied("You can only update evidence fields")

        # Staff can update resolution; set resolved_at timestamp when it changes
        new_resolution = serializer.validated_data.get("resolution")
        if new_resolution and new_resolution != instance.resolution:
            if not self.request.user.is_staff:
                raise PermissionDenied("Only admins can update resolution")
            serializer.validated_data["resolved_at"] = timezone.now()

        serializer.save()


class TradeDisputeListView(generics.ListAPIView):
    """List all disputes belonging to the authenticated user."""

    serializer_class = TradeDisputeSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["resolution"]
    search_fields = ["trade__id", "initiator_token"]
    ordering = ["-created_at"]

    def get_queryset(self):
        client_token = self.request.user.client_token
        hmac_key = settings.XUSDT_SETTINGS["USER_TOKEN_HMAC_KEY"].encode()
        user_token = hmac.new(hmac_key, client_token.encode(), hashlib.sha256).hexdigest()

        qs = TradeDispute.objects.filter(
            Q(trade__buyer_token=user_token)
            | Q(trade__seller_token=user_token)
            | Q(initiator_token=user_token)
        )

        # Optional filtering by resolution query param
        resolution = self.request.query_params.get("resolution")
        if resolution is not None:
            qs = qs.filter(resolution=resolution)

        return qs.order_by("-created_at")
