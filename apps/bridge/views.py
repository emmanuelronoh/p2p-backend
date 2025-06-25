from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import (
    BridgeNetwork, BridgeToken, BridgeTokenNetwork,
    BridgeQuote, BridgeTransaction, BridgeFee, BridgeStats
)
from .serializers import (
    NetworkSerializer, TokenSerializer, TokenNetworkSerializer,
    QuoteSerializer, TransactionSerializer, FeeSerializer, StatsSerializer
)
import uuid
from django.db.models import Q
from rest_framework import status
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal, InvalidOperation
import logging

logger = logging.getLogger(__name__)
class NetworkListView(APIView):
    def get(self, request):
        networks = BridgeNetwork.objects.filter(is_active=True)
        serializer = NetworkSerializer(networks, many=True)
        return Response(serializer.data)

class TokenListView(APIView):
    def get(self, request):
        network_id = request.query_params.get('network_id')
        
        tokens = BridgeToken.objects.filter(is_active=True)
        
        if network_id:
            tokens = tokens.filter(
                bridgetokennetwork__network_id=network_id,
                bridgetokennetwork__is_active=True
            ).distinct()
            
        serializer = TokenSerializer(tokens, many=True)
        return Response(serializer.data)

class TokenNetworkListView(APIView):
    def get(self, request, token_id):
        token_networks = BridgeTokenNetwork.objects.filter(
            token_id=token_id,
            is_active=True
        )
        serializer = TokenNetworkSerializer(token_networks, many=True)
        return Response(serializer.data)



class QuoteCreateView(APIView):
    def post(self, request):
        logger.info(f"Received bridge quote request: {request.data}")
        
        try:
            required_fields = ['token', 'amount', 'from_network', 'to_network']
            if not all(field in request.data for field in required_fields):
                missing = [f for f in required_fields if f not in request.data]
                return Response(
                    {'error': f'Missing required fields: {", ".join(missing)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            token_id = request.data['token']
            from_network_id = request.data['from_network']
            to_network_id = request.data['to_network']

            # Validate amount
            try:
                amount = Decimal(str(request.data['amount']))
                if amount <= 0:
                    raise ValueError("Amount must be positive")
            except (InvalidOperation, ValueError, TypeError):
                logger.warning(f"Invalid amount: {request.data.get('amount')}")
                return Response(
                    {'error': 'Invalid amount - must be a positive number'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Fetch token and networks
            try:
                token = BridgeToken.objects.get(id=token_id, is_active=True)
                from_network = BridgeNetwork.objects.get(id=from_network_id, is_active=True)
                to_network = BridgeNetwork.objects.get(id=to_network_id, is_active=True)
            except BridgeToken.DoesNotExist:
                logger.warning(f"Token not found: {token_id}")
                available_tokens = list(BridgeToken.objects.filter(is_active=True).values('id', 'symbol'))
                return Response(
                    {'error': 'Token not found or inactive', 'available_tokens': available_tokens},
                    status=status.HTTP_400_BAD_REQUEST
                )
            except BridgeNetwork.DoesNotExist:
                logger.warning(f"Network not found: from={from_network_id}, to={to_network_id}")
                available_networks = list(BridgeNetwork.objects.filter(is_active=True).values('id', 'name'))
                return Response(
                    {'error': 'Network not found or inactive', 'available_networks': available_networks},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Token availability check
            token_from = BridgeTokenNetwork.objects.filter(token=token, network=from_network, is_active=True).first()
            token_to = BridgeTokenNetwork.objects.filter(token=token, network=to_network, is_active=True).first()

            if not token_from or not token_to:
                logger.warning(f"Token {token.symbol} not available on required networks")
                supported_networks = list(
                    BridgeTokenNetwork.objects.filter(token=token, is_active=True)
                    .values_list('network__name', flat=True)
                )
                return Response(
                    {
                        'error': 'Token not available on one or both networks',
                        'details': {
                            'token': token.symbol,
                            'supported_networks': supported_networks
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Check minimum amount
            if amount < token_from.min_bridge_amount:
                logger.warning(
                    f"Amount {amount} is below minimum {token_from.min_bridge_amount} for {token.symbol}"
                )
                return Response(
                    {
                        'error': 'Amount below minimum bridge requirement',
                        'minimum_amount': str(token_from.min_bridge_amount),
                        'currency': token.symbol
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Get fee configuration
            fee = BridgeFee.objects.filter(
                from_network=from_network,
                to_network=to_network,
                token=token,
                is_active=True
            ).first()

            if not fee:
                logger.warning(f"No bridge fee config for {token.symbol} from {from_network.name} to {to_network.name}")
                available_routes = list(
                    BridgeFee.objects.filter(token=token, is_active=True)
                    .values('from_network__name', 'to_network__name')
                )
                return Response(
                    {'error': 'No available bridge route', 'available_routes': available_routes},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Calculate fee
            try:
                percentage_fee = amount * fee.fee_percentage / 100
                fee_amount = max(percentage_fee, fee.min_fee)
                if fee.max_fee is not None:
                    fee_amount = min(fee_amount, fee.max_fee)
                if fee_amount >= amount:
                    raise ValueError("Fee exceeds or equals amount")
            except Exception as e:
                logger.error(f"Fee calculation failed: {str(e)}")
                return Response({'error': 'Invalid fee configuration'}, status=500)

            # Create quote
            try:
                quote = BridgeQuote.objects.create(
                    token=token,
                    amount=amount,
                    from_network=from_network,
                    to_network=to_network,
                    fee_amount=fee_amount,
                    estimated_time=self._calculate_estimated_time(from_network, to_network),
                    valid_until=timezone.now() + timedelta(minutes=5)
                )
                logger.info(f"Created quote {quote.id} for {amount} {token.symbol}")
                serializer = QuoteSerializer(quote)
                return Response(serializer.data)
            except Exception as e:
                logger.error(f"Quote creation failed: {str(e)}")
                return Response({'error': 'Failed to create quote'}, status=500)

        except Exception as e:
            logger.error(f"Unexpected error in QuoteCreateView: {str(e)}", exc_info=True)
            return Response({'error': 'Internal server error'}, status=500)

    def _calculate_estimated_time(self, from_network, to_network):
        """Calculate estimated bridge time based on network characteristics"""
        base_time = 30  # in minutes
        if from_network.is_evm and to_network.is_evm:
            return base_time
        return base_time * 2



class InitiateBridgeView(APIView):
    def post(self, request):
        quote_id = request.data.get('quote_id')
        from_address = request.data.get('from_address') or request.data.get('user_address')
        to_address = request.data.get('to_address') or request.data.get('destination_address')
        user_token = request.headers.get('X-Client-Token')  # Get from auth
        
        try:
            quote = BridgeQuote.objects.get(id=quote_id, valid_until__gte=timezone.now())
            
            # Create bridge transaction
            bridge = BridgeTransaction.objects.create(
                user_token=user_token,
                quote=quote,
                from_address=from_address,
                to_address=to_address,
                status='pending'
            )
            
            # In a real app, here you'd interact with blockchain
            # For now, we'll simulate success
            bridge.status = 'completed'
            bridge.completed_at = timezone.now()
            bridge.save()
            
            serializer = TransactionSerializer(bridge)
            return Response(serializer.data)
            
        except BridgeQuote.DoesNotExist:
            return Response(
                {'error': 'Invalid or expired quote'},
                status=status.HTTP_400_BAD_REQUEST
            )

class BridgeStatusView(APIView):
    def get(self, request, id):
        try:
            bridge = BridgeTransaction.objects.get(id=id)
            serializer = TransactionSerializer(bridge)
            return Response(serializer.data)
        except BridgeTransaction.DoesNotExist:
            return Response(
                {'error': 'Bridge not found'},
                status=status.HTTP_404_NOT_FOUND
            )

class BridgeHistoryView(APIView):
    def get(self, request):
        user_token = request.headers.get('X-Client-Token')
        bridges = BridgeTransaction.objects.filter(user_token=user_token).order_by('-initiated_at')
        serializer = TransactionSerializer(bridges, many=True)
        return Response(serializer.data)

class EstimateTimeView(APIView):
    def get(self, request):
        from_network_id = request.query_params.get('from_network')
        to_network_id = request.query_params.get('to_network')
        
        try:
            from_network = BridgeNetwork.objects.get(id=from_network_id, is_active=True)
            to_network = BridgeNetwork.objects.get(id=to_network_id, is_active=True)
            
            # Simplified - in real app use historical data
            avg_time = 30  # minutes
            
            return Response({'estimated_time': avg_time})
            
        except BridgeNetwork.DoesNotExist:
            return Response(
                {'error': 'Invalid network'},
                status=status.HTTP_400_BAD_REQUEST
            )

class FeeListView(APIView):
    def get(self, request):
        from_network_id = request.query_params.get('from_network')
        to_network_id = request.query_params.get('to_network')
        token_symbol = request.query_params.get('token')
        
        fees = BridgeFee.objects.all()
        
        if from_network_id:
            fees = fees.filter(from_network_id=from_network_id)
        if to_network_id:
            fees = fees.filter(to_network_id=to_network_id)
        if token_symbol:
            fees = fees.filter(token__symbol=token_symbol)
            
        serializer = FeeSerializer(fees, many=True)
        return Response(serializer.data)

class StatsView(APIView):
    def get(self, request):
        stats = BridgeStats.objects.all()
        serializer = StatsSerializer(stats, many=True)
        return Response(serializer.data)