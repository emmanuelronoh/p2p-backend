from rest_framework import generics, permissions, status
from rest_framework.response import Response
from .models import P2PListing, P2PTrade
from .serializers import P2PListingSerializer, P2PTradeSerializer, P2PTradeCreateSerializer
from django.utils import timezone
from django.conf import settings
from django.db.models import Q
from rest_framework import serializers
import hmac
import hashlib
from rest_framework.views import APIView
from django.db.models import Avg, Count, Min, Max, Sum
from rest_framework.permissions import IsAuthenticated
from .utils import create_escrow_wallet

class P2PListingListView(generics.ListCreateAPIView):
    """List active listings and allow authenticated users to create a listing."""

    serializer_class = P2PListingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            P2PListing.objects.filter(status=1, expires_at__gt=timezone.now())
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        # Validate required fields - using usdt_amount instead of fiat_amount
        required_fields = [
            "crypto_type",
            "crypto_amount",
            "crypto_currency",
            "usdt_amount",
            "fiat_currency",
            "payment_method",
        ]
        for field in required_fields:
            if field not in serializer.validated_data:
                raise serializers.ValidationError({field: "This field is required"})

        # Generate seller token
        client_token = self.request.user.client_token
        hmac_key = settings.XUSDT_SETTINGS["USER_TOKEN_HMAC_KEY"].encode()
        seller_token = hmac.new(hmac_key, client_token.encode(), hashlib.sha256).hexdigest()

        # Create escrow wallet
        escrow_wallet = create_escrow_wallet()
        escrow_wallet.user_token = seller_token
        escrow_wallet.status = 'created'
        escrow_wallet.save()

        # Save listing with seller_token, status, and escrow_wallet
        serializer.save(
            seller_token=seller_token,
            status=1,
            escrow_wallet=escrow_wallet
        )

class P2PListingDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a single listing while it is not expired."""

    serializer_class = P2PListingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return P2PListing.objects.filter(expires_at__gt=timezone.now())



class P2PTradeCreateView(generics.CreateAPIView):
    """Create a new trade from an active, funded listing."""

    queryset = P2PTrade.objects.all()
    serializer_class = P2PTradeCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        listing = serializer.validated_data["listing"]

        # Generate user token
        client_token = self.request.user.client_token
        hmac_key = settings.XUSDT_SETTINGS["USER_TOKEN_HMAC_KEY"].encode()
        user_token = hmac.new(hmac_key, client_token.encode(), hashlib.sha256).hexdigest()

        # Prevent self-trading
        if user_token == listing.seller_token:
            raise serializers.ValidationError(
                {"listing": "You cannot create a trade with your own listing"}
            )

        # Check if listing is active and not expired
        if listing.status != 1 or listing.expires_at < timezone.now():
            raise serializers.ValidationError(
                {"listing": "This listing is not available for trading"}
            )

        # Ensure the listing is funded
        if (
            listing.escrow_wallet is None
            or listing.escrow_wallet.status != "funded"
            or listing.status != 2  # Listing must have status = 2 (Funded)
        ):
            raise serializers.ValidationError(
                {"listing": "Listing must be funded by merchant first"}
            )

        # Create and save the trade
        trade = serializer.save(
            buyer_token=user_token,
            seller_token=listing.seller_token,
            status=1  # Trade status = Funded
        )

        # Calculate and save fee
        trade.calculate_fee()
        trade.save()

        # Reserve the listing
        listing.status = 3  # Reserved
        listing.save()


class P2PTradeDetailView(generics.RetrieveUpdateAPIView):
    """Retrieve or update a trade visible to either the buyer or the seller."""

    serializer_class = P2PTradeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        client_token = self.request.user.client_token
        hmac_key = settings.XUSDT_SETTINGS["USER_TOKEN_HMAC_KEY"].encode()
        user_token = hmac.new(hmac_key, client_token.encode(), hashlib.sha256).hexdigest()
        return P2PTrade.objects.filter(Q(buyer_token=user_token) | Q(seller_token=user_token))


class MyTradesListView(generics.ListAPIView):
    """List all trades where the authenticated user is either buyer or seller."""

    serializer_class = P2PTradeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        client_token = self.request.user.client_token
        hmac_key = settings.XUSDT_SETTINGS["USER_TOKEN_HMAC_KEY"].encode()
        user_token = hmac.new(hmac_key, client_token.encode(), hashlib.sha256).hexdigest()
        return (
            P2PTrade.objects.filter(Q(buyer_token=user_token) | Q(seller_token=user_token))
            .order_by("-created_at")
        )
    
class MarketStatsView(APIView):
    """Provides market statistics for P2P trading"""
    authentication_classes = []
    permission_classes = []

    def get(self, request, format=None):
        # Get active listings
        active_listings = P2PListing.objects.filter(
            status=1,  # Active
            expires_at__gt=timezone.now()
        )
        
        # Calculate statistics - using usdt_amount instead of fiat_amount
        stats = {
            'total_active_listings': active_listings.count(),
            'average_price': active_listings.aggregate(avg_price=Avg('usdt_amount'))['avg_price'],
            'min_price': active_listings.aggregate(min_price=Min('usdt_amount'))['min_price'],
            'max_price': active_listings.aggregate(max_price=Max('usdt_amount'))['max_price'],
            'payment_methods_distribution': active_listings.values('payment_method').annotate(
                count=Count('payment_method')
            ).order_by('-count'),
            'volume_24h': P2PTrade.objects.filter(
                created_at__gte=timezone.now() - timezone.timedelta(days=1)
            ).aggregate(total_volume=Sum('usdt_amount'))['total_volume'] or 0,
        }
        
        return Response(stats)

class MarkTradeAsPaidView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        try:
            trade = P2PTrade.objects.get(pk=kwargs['pk'])

            # Check if user is the buyer
            client_token = request.user.client_token
            hmac_key = settings.XUSDT_SETTINGS["USER_TOKEN_HMAC_KEY"].encode()
            user_token = hmac.new(hmac_key, client_token.encode(), hashlib.sha256).hexdigest()

            if trade.buyer_token != user_token:
                return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

            if trade.status != 1:  # Must be in Funded state
                return Response(
                    {"detail": "Trade must be in Funded state to mark as paid."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Update status to PaymentSent
            trade.status = 2
            trade.updated_at = timezone.now()
            trade.save()

            serializer = P2PTradeSerializer(trade)
            return Response(serializer.data)

        except P2PTrade.DoesNotExist:
            return Response({"detail": "Trade not found."}, status=status.HTTP_404_NOT_FOUND)
        
        
class SpecificUserView(APIView):
    """
    Get listings for a specific user or current user if no ID provided
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user_id = request.query_params.get('user_id')
        
        # If no user_id provided, get current user's token
        if not user_id:
            client_token = request.user.client_token
            hmac_key = settings.XUSDT_SETTINGS["USER_TOKEN_HMAC_KEY"].encode()
            user_id = hmac.new(hmac_key, client_token.encode(), hashlib.sha256).hexdigest()

        listings = P2PListing.objects.filter(
            seller_token=user_id,
            expires_at__gt=timezone.now()
        ).order_by('-created_at')

        serializer = P2PListingSerializer(listings, many=True)
        return Response({
            "listings": serializer.data,
            "user_info": {
                "id": user_id,
                # Add other user info if available
            }
        })