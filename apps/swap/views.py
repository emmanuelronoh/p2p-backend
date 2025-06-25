from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import (
    SwapToken, SwapRoute, SwapQuote, SwapTransaction,
    SwapAllowance, SwapPrice, MarketStats
)
from .serializers import (
    TokenSerializer, RouteSerializer, QuoteSerializer,
    TransactionSerializer, AllowanceSerializer,
    PriceSerializer, MarketStatsSerializer
)
import uuid
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q
from decimal import Decimal, InvalidOperation
from .models import SwapToken, SwapRoute, SwapQuote
import logging

logger = logging.getLogger(__name__)

class TokenListView(APIView):
    def get(self, request):
        tokens = SwapToken.objects.filter(is_active=True)
        serializer = TokenSerializer(tokens, many=True)
        return Response(serializer.data)

class RouteListView(APIView):
    def get(self, request):
        token_in = request.query_params.get('token_in')
        token_out = request.query_params.get('token_out')
        
        routes = SwapRoute.objects.filter(is_active=True)
        
        if token_in:
            routes = routes.filter(token_in__symbol=token_in)
        if token_out:
            routes = routes.filter(token_out__symbol=token_out)
            
        serializer = RouteSerializer(routes, many=True)
        return Response(serializer.data)



class QuoteCreateView(APIView):
    def post(self, request):
        """
        Create a swap quote between two tokens with amount validation and route checking
        """
        # Input validation and logging
        logger.info(f"Received swap request: {request.data}")
        
        try:
            # Validate required fields
            required_fields = ['token_in', 'token_out', 'amount_in']
            if not all(field in request.data for field in required_fields):
                missing = [f for f in required_fields if f not in request.data]
                return Response(
                    {'error': f'Missing required fields: {", ".join(missing)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            token_in_symbol = request.data['token_in'].strip().upper()
            token_out_symbol = request.data['token_out'].strip().upper()
            
            try:
                amount_in = Decimal(str(request.data['amount_in']))
                if amount_in <= 0:
                    raise ValueError("Amount must be positive")
            except (InvalidOperation, ValueError, TypeError) as e:
                logger.warning(f"Invalid amount: {request.data.get('amount_in')}")
                return Response(
                    {'error': 'Invalid amount - must be a positive number'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Get tokens with case-insensitive search and active status check
            try:
                token_in = SwapToken.objects.get(
                    symbol__iexact=token_in_symbol,
                    is_active=True
                )
                token_out = SwapToken.objects.get(
                    symbol__iexact=token_out_symbol,
                    is_active=True
                )
            except SwapToken.DoesNotExist:
                logger.warning(f"Token not found: in={token_in_symbol}, out={token_out_symbol}")
                available_tokens = list(SwapToken.objects.filter(
                    is_active=True
                ).values_list('symbol', flat=True))
                return Response(
                    {
                        'error': 'Invalid token symbol',
                        'available_tokens': available_tokens
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Check if route exists with amount validation
            route = SwapRoute.objects.filter(
                token_in=token_in,
                token_out=token_out,
                is_active=True,
                min_amount_in__lte=amount_in,
                max_amount_in__gte=amount_in
            ).first()
            
            if not route:
                logger.warning(
                    f"No route found: {token_in_symbol}→{token_out_symbol} "
                    f"for amount {amount_in}"
                )
                available_routes = list(SwapRoute.objects.filter(
                    is_active=True
                ).values(
                    'token_in__symbol',
                    'token_out__symbol',
                    'min_amount_in',
                    'max_amount_in'
                ))
                return Response(
                    {
                        'error': 'No available route for this swap',
                        'details': {
                            'requested_amount': str(amount_in),
                            'available_routes': available_routes
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Calculate swap with proper decimal handling
            try:
                rate = self._get_current_rate(token_in, token_out)  # Replace with actual oracle call
                fee_percentage = Decimal(route.fee_percentage)
                
                amount_out = amount_in * rate * (1 - fee_percentage / 100)
                fee_amount = amount_in * fee_percentage / 100
                
                # Validate output amount is positive
                if amount_out <= 0:
                    raise ValueError("Invalid swap output amount")
                    
            except Exception as e:
                logger.error(f"Swap calculation error: {str(e)}")
                return Response(
                    {'error': 'Failed to calculate swap terms'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # Create quote with additional validation
            try:
                quote = SwapQuote.objects.create(
                    token_in=token_in,
                    token_out=token_out,
                    amount_in=amount_in,
                    amount_out=amount_out,
                    rate=rate,
                    fee_amount=fee_amount,
                    # route=route,
                    valid_until=timezone.now() + timedelta(minutes=30)
                )
                
                logger.info(
                    f"Created quote {quote.id}: "
                    f"{amount_in} {token_in_symbol} → {amount_out} {token_out_symbol} "
                    f"(Fee: {fee_amount} {token_in_symbol})"
                )
                
                serializer = QuoteSerializer(quote)
                return Response(serializer.data)
                
            except Exception as e:
                logger.error(f"Quote creation failed: {str(e)}")
                return Response(
                    {'error': 'Failed to create quote'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        except Exception as e:
            logger.error(f"Unexpected error in QuoteCreateView: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Internal server error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _get_current_rate(self, token_in, token_out):
        """
        Get current exchange rate between tokens
        Replace this with actual oracle/price feed implementation
        """
        # TODO: Implement actual rate fetching from oracle
        return Decimal('1.0')  # Temporary fixed rate
    

class ExecuteSwapView(APIView):
    def post(self, request):
        try:
            # Input validation
            required_fields = ['quote_id', 'from_address', 'to_address']
            if not all(field in request.data for field in required_fields):
                missing = [f for f in required_fields if f not in request.data]
                return Response(
                    {'error': f'Missing required fields: {", ".join(missing)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            quote_id = request.data['quote_id']
            from_address = request.data['from_address']
            to_address = request.data['to_address']
            user_token = request.headers.get('X-Client-Token', '')  # Get from auth

            # Validate address format (basic check)
            if not (from_address.startswith('0x') and len(from_address) == 42):
                return Response(
                    {'error': 'Invalid from_address format'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                quote = SwapQuote.objects.get(
                    id=quote_id,
                    valid_until__gte=timezone.now()
                )
                
                # Create swap transaction
                swap = SwapTransaction.objects.create(
                    user_token=user_token,
                    quote=quote,
                    from_address=from_address,
                    to_address=to_address,
                    status='pending'
                )
                
                # TODO: Actual blockchain interaction would go here
                # For simulation:
                swap.status = 'completed'
                swap.executed_at = timezone.now()
                swap.completed_at = timezone.now()
                swap.save()
                
                logger.info(f"Swap executed successfully: {swap.id}")
                serializer = TransactionSerializer(swap)
                return Response(serializer.data)
                
            except SwapQuote.DoesNotExist:
                # More detailed error message
                exists = SwapQuote.objects.filter(id=quote_id).exists()
                if exists:
                    quote = SwapQuote.objects.get(id=quote_id)
                    return Response(
                        {
                            'error': 'Quote expired',
                            'valid_until': quote.valid_until,
                            'current_time': timezone.now()
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
                else:
                    return Response(
                        {'error': 'Quote not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )
                    
        except Exception as e:
            logger.error(f"Swap execution failed: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Internal server error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        

class SwapStatusView(APIView):
    def get(self, request, tx_id):
        try:
            swap = SwapTransaction.objects.get(id=tx_id)
            serializer = TransactionSerializer(swap)
            return Response(serializer.data)
        except SwapTransaction.DoesNotExist:
            return Response(
                {'error': 'Swap not found'},
                status=status.HTTP_404_NOT_FOUND
            )

class SwapHistoryView(APIView):
    def get(self, request):
        user_token = request.headers.get('X-Client-Token')
        swaps = SwapTransaction.objects.filter(user_token=user_token).order_by('-created_at')
        serializer = TransactionSerializer(swaps, many=True)
        return Response(serializer.data)

class PriceListView(APIView):
    def get(self, request):
        token = request.query_params.get('token')
        prices = SwapPrice.objects.all()
        
        if token:
            prices = prices.filter(token__symbol=token)
            
        prices = prices.order_by('-timestamp')[:100]  # Limit to 100 most recent
        serializer = PriceSerializer(prices, many=True)
        return Response(serializer.data)

class MarketStatsView(APIView):
    def get(self, request):
        pair = request.query_params.get('pair')
        stats = MarketStats.objects.all()
        
        if pair:
            stats = stats.filter(token_pair=pair)
            
        serializer = MarketStatsSerializer(stats, many=True)
        return Response(serializer.data)

class AllowanceView(APIView):
    def get(self, request):
        user_token = request.headers.get('X-Client-Token')
        token = request.query_params.get('token')
        
        allowances = SwapAllowance.objects.filter(user_token=user_token)
        
        if token:
            allowances = allowances.filter(token__symbol=token)
            
        serializer = AllowanceSerializer(allowances, many=True)
        return Response(serializer.data)

    def post(self, request):
        user_token = request.headers.get('X-Client-Token')
        token_symbol = request.data.get('token')
        contract_address = request.data.get('contract_address')
        amount = request.data.get('amount')
        
        try:
            token = SwapToken.objects.get(symbol=token_symbol)
            amount = Decimal(amount)
            
            # Update or create allowance
            allowance, created = SwapAllowance.objects.update_or_create(
                user_token=user_token,
                token=token,
                contract_address=contract_address,
                defaults={'allowance_amount': amount}
            )
            
            serializer = AllowanceSerializer(allowance)
            return Response(serializer.data)
            
        except SwapToken.DoesNotExist:
            return Response(
                {'error': 'Invalid token'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except (ValueError, TypeError):
            return Response(
                {'error': 'Invalid amount'},
                status=status.HTTP_400_BAD_REQUEST
            )