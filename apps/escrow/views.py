from rest_framework import generics, permissions, status
from rest_framework.response import Response
from .models import EscrowWallet, SystemWallet
from .serializers import EscrowWalletSerializer, SystemWalletSerializer
from django.conf import settings
from apps.p2p.models import P2PListing
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from .services import release_to, wait_for_deposit
from decimal import Decimal
from .services import create_escrow_wallet
from django.utils import timezone
import hmac
import hashlib

class EscrowWalletCreateView(generics.CreateAPIView):
    queryset = EscrowWallet.objects.all()
    serializer_class = EscrowWalletSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        client_token = self.request.user.client_token
        user_token = EscrowWallet.generate_user_token(client_token)
        
        # Create and save the escrow wallet with all fields at once
        escrow_wallet = create_escrow_wallet()
        escrow_wallet.user_token = user_token
        escrow_wallet.status = 'created'
        escrow_wallet.save()
        
        # Return the created instance through the serializer
        serializer.instance = escrow_wallet

class EscrowWalletDetailView(generics.RetrieveAPIView):
    serializer_class = EscrowWalletSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        client_token = self.request.user.client_token
        user_token = EscrowWallet.generate_user_token(client_token)
        return EscrowWallet.objects.filter(user_token=user_token)

class SystemWalletListView(generics.ListAPIView):
    queryset = SystemWallet.objects.all()
    serializer_class = SystemWalletSerializer
    permission_classes = [permissions.IsAdminUser]

class EscrowWalletListView(generics.ListAPIView):
    serializer_class = EscrowWalletSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        client_token = self.request.user.client_token
        user_token = EscrowWallet.generate_user_token(client_token)
        return EscrowWallet.objects.filter(user_token=user_token)

class EscrowFundView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, escrow_id):
        escrow = get_object_or_404(EscrowWallet, id=escrow_id)
        
        # Verify user owns this escrow
        client_token = request.user.client_token
        user_token = EscrowWallet.generate_user_token(client_token)
        if escrow.user_token != user_token:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)
        
        # Start monitoring for deposit
        try:
            min_amount = Decimal(request.data.get('min_amount', 0))
            wait_for_deposit(escrow, min_amount)
            return Response({"status": "waiting_for_deposit"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class EscrowStatusView(APIView):
    def get(self, request, listing_id):
        listing = get_object_or_404(P2PListing, id=listing_id)

        # Ensure the listing has an escrow_wallet attached
        if not listing.escrow_wallet:
            return Response(
                {"detail": "No escrow wallet linked to this listing."},
                status=status.HTTP_404_NOT_FOUND
            )

        escrow = listing.escrow_wallet

        return Response({
            "id": str(escrow.id),
            "status": escrow.status
        }, status=status.HTTP_200_OK)
    
    
class EscrowReleaseView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, escrow_id):
        escrow = get_object_or_404(EscrowWallet, id=escrow_id)
        
        # Verify user owns this escrow
        client_token = request.user.client_token
        user_token = EscrowWallet.generate_user_token(client_token)
        if escrow.user_token != user_token:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)
        
        if escrow.status != "funded":
            return Response(
                {"error": "Escrow not in fundable state"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not escrow.buyer_address:
            return Response(
                {"error": "Buyer address not set"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            tx_hash = release_to(
                buyer_addr=escrow.buyer_address,
                wallet=escrow,
                amount=escrow.amount,
                fee=Decimal(settings.ESCROW_FEE_PERCENT) * escrow.amount
            )
            
            return Response(
                {"tx_hash": tx_hash, "status": "released"},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"error": f"Release failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class EscrowDisputeView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, escrow_id):
        escrow = get_object_or_404(EscrowWallet, id=escrow_id)
        
        # Verify user owns this escrow
        client_token = request.user.client_token
        user_token = EscrowWallet.generate_user_token(client_token)
        if escrow.user_token != user_token:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)
        
        if escrow.status != "funded":
            return Response(
                {"error": "Only funded escrows can be disputed"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        escrow.status = "disputed"
        escrow.save(update_fields=["status"])
        
        # Here you would typically notify admins via email or other channel
        # and potentially freeze the funds
        
        return Response(
            {"status": "disputed", "message": "Dispute opened successfully"},
            status=status.HTTP_200_OK
        )

class EscrowUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def patch(self, request, escrow_id):
        escrow = get_object_or_404(EscrowWallet, id=escrow_id)
        
        # Verify user owns this escrow
        client_token = request.user.client_token
        user_token = EscrowWallet.generate_user_token(client_token)
        if escrow.user_token != user_token:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)
        
        if escrow.status != "created":
            return Response(
                {"error": "Can only update escrow in created state"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update buyer/seller addresses
        buyer_address = request.data.get('buyer_address')
        seller_address = request.data.get('seller_address')
        
        if buyer_address:
            escrow.buyer_address = buyer_address
        if seller_address:
            escrow.seller_address = seller_address
        
        escrow.save(update_fields=["buyer_address", "seller_address"])
        
        return Response(
            EscrowWalletSerializer(escrow).data,
            status=status.HTTP_200_OK
        )
    

class FundEscrowView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, listing_id):
        listing = get_object_or_404(P2PListing, id=listing_id)
        
        # Verify user owns this listing
        client_token = request.user.client_token
        hmac_key = settings.XUSDT_SETTINGS["USER_TOKEN_HMAC_KEY"].encode()
        user_token = hmac.new(hmac_key, client_token.encode(), hashlib.sha256).hexdigest()
        
        if listing.seller_token != user_token:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)
            
        if not listing.escrow_wallet:
            return Response({"error": "No escrow wallet"}, status=status.HTTP_400_BAD_REQUEST)
            
        # Convert amount to USDT wei
        amount = listing.crypto_amount
        amount_wei = int(amount * (10 ** 6))  # USDT has 6 decimals
        
        # Get merchant's wallet address from request
        merchant_wallet = request.data.get('merchant_wallet')
        if not merchant_wallet:
            return Response({"error": "Merchant wallet required"}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            # Transfer from merchant to escrow
            tx_hash = transfer_usdt(
                from_address=merchant_wallet,
                to_address=listing.escrow_wallet.address,
                amount_wei=amount_wei
            )
            
            # Update escrow status
            listing.escrow_wallet.mark_as_funded(amount)
            listing.status = 2  # Funded
            listing.save()
            
            return Response({
                "status": "funded",
                "tx_hash": tx_hash,
                "escrow_address": listing.escrow_wallet.address
            })
            
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        


class ReleaseEscrowView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, trade_id):
        trade = get_object_or_404(P2PTrade, id=trade_id)
        listing = trade.listing
        
        # Verify user is the merchant
        client_token = request.user.client_token
        hmac_key = settings.XUSDT_SETTINGS["USER_TOKEN_HMAC_KEY"].encode()
        user_token = hmac.new(hmac_key, client_token.encode(), hashlib.sha256).hexdigest()
        
        if listing.seller_token != user_token:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)
            
        if trade.status != 2:  # Must be in PaymentSent state
            return Response(
                {"error": "Trade must be in PaymentSent state"},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        try:
            # Release funds from escrow to buyer
            tx_hash = release_to(
                buyer_addr=request.data.get('buyer_wallet'),
                wallet=listing.escrow_wallet,
                amount=listing.crypto_amount,
                fee=trade.fee_amount
            )
            
            # Update statuses
            trade.status = 3  # Completed
            trade.completed_at = timezone.now()
            trade.save()
            
            listing.status = 4  # Completed
            listing.save()
            
            return Response({
                "status": "completed",
                "tx_hash": tx_hash
            })
            
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)