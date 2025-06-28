from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from .blockchain import BlockchainManager
from .models import Transaction, DepositAddress, Wallet
import time
import logging
from datetime import datetime, timedelta
from django.utils import timezone
from decimal import Decimal

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_withdrawal(self, transaction_id):
    """
    Process cryptocurrency withdrawals asynchronously
    Handles USDT (ERC20/TRC20), BTC, and ETH transactions
    Implements retry logic for transient failures
    """
    transaction = Transaction.objects.get(id=transaction_id)
    blockchain = BlockchainManager()
    
    try:
        # Additional validation before processing
        if transaction.status != 'pending':
            logger.warning(f"Transaction {transaction_id} is not pending, status: {transaction.status}")
            return

        if transaction.type != 'withdrawal':
            logger.error(f"Transaction {transaction_id} is not a withdrawal")
            return

        # Get network for USDT transactions
        network = None
        if transaction.currency.code == 'USDT':
            if not transaction.network:
                logger.error(f"USDT transaction {transaction_id} missing network")
                transaction.status = 'failed'
                transaction.save()
                return
            network = transaction.network

        logger.info(f"Processing {transaction.currency.code} withdrawal of {transaction.amount} to {transaction.address}")

        tx_hash = blockchain.send_transaction(
            currency=transaction.currency.code,
            to_address=transaction.address,
            amount=transaction.amount,
            network=network,
            memo=transaction.memo or ''
        )
        
        if tx_hash:
            transaction.status = 'completed'
            transaction.txid = tx_hash if isinstance(tx_hash, str) else tx_hash.hex()
            transaction.completed_at = timezone.now()
            
            # Only unlock if the transaction was pending
            if transaction.wallet.locked >= transaction.amount:
                transaction.wallet.locked -= transaction.amount
            else:
                logger.error(f"Inconsistent locked amount for wallet {transaction.wallet.id}")
            
            transaction.wallet.save()
            transaction.save()
            
            logger.info(f"Successfully processed withdrawal {transaction_id} with txid {transaction.txid}")
        else:
            raise Exception("Blockchain manager returned no transaction hash")

    except Exception as e:
        logger.error(f"Error processing withdrawal {transaction_id}: {str(e)}")
        
        try:
            # Attempt to retry for transient failures
            if isinstance(e, (ConnectionError, TimeoutError)):
                self.retry(exc=e)
            
            transaction.status = 'failed'
            transaction.error_message = str(e)[:255]  # Truncate to fit in field
            
            # Return the funds to available balance
            if transaction.wallet.locked >= transaction.amount:
                transaction.wallet.locked -= transaction.amount
                transaction.wallet.balance += transaction.amount
                transaction.wallet.save()
            else:
                logger.error(f"Cannot return funds for failed transaction {transaction_id} - locked amount mismatch")
            
            transaction.save()
            
            # Notify administrators or monitoring system
            # notify_admin.delay(f"Withdrawal failed for transaction {transaction_id}")
            
        except MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for transaction {transaction_id}")
            transaction.status = 'failed'
            transaction.error_message = "Max retries exceeded"
            transaction.save()

@shared_task
def check_deposit_status(deposit_address_id):
    """
    Monitor deposit addresses for incoming transactions
    Handles USDT (ERC20/TRC20), BTC, and ETH deposits
    """
    deposit_address = DepositAddress.objects.get(id=deposit_address_id)
    blockchain = BlockchainManager()
    last_checked = timezone.now()
    
    logger.info(f"Starting deposit monitoring for address {deposit_address.address}")
    
    try:
        while deposit_address.is_active:
            try:
                # Get current balance from blockchain
                current_balance = blockchain.get_address_balance(
                    deposit_address.currency.code,
                    deposit_address.address
                )
                
                # Convert to Decimal for consistency
                current_balance = Decimal(str(current_balance)) if current_balance is not None else Decimal('0')
                
                # Check if we have new deposits
                if current_balance > Decimal('0'):
                    logger.info(f"New deposit detected: {current_balance} {deposit_address.currency.code}")
                    
                    # Get or create wallet
                    wallet, created = Wallet.objects.get_or_create(
                        user=deposit_address.user,
                        currency=deposit_address.currency,
                        defaults={'balance': 0, 'locked': 0}
                    )
                    
                    # Calculate the actual deposit amount (handle multiple deposits)
                    deposited_amount = current_balance
                    if not created and wallet.address == deposit_address.address:
                        # If this is the wallet's main address, we need to track individual deposits
                        # This requires more sophisticated tracking in a real implementation
                        deposited_amount = current_balance - wallet.balance
                    
                    if deposited_amount > Decimal('0'):
                        # Create deposit transaction
                        Transaction.objects.create(
                            user=deposit_address.user,
                            wallet=wallet,
                            currency=deposit_address.currency,
                            amount=deposited_amount,
                            type='deposit',
                            status='completed',
                            address=deposit_address.address,
                            network=deposit_address.currency.network if deposit_address.currency.code == 'USDT' else None
                        )
                        
                        # Update wallet balance
                        wallet.balance += deposited_amount
                        wallet.save()
                        
                        logger.info(f"Created deposit of {deposited_amount} {deposit_address.currency.code} for user {deposit_address.user.id}")
                    
                    # For one-time addresses, deactivate after first deposit
                    if not deposit_address.reusable:
                        deposit_address.is_active = False
                        deposit_address.save()
                        break
                
                # Update last checked time
                deposit_address.last_checked = timezone.now()
                deposit_address.save()
                
                # Sleep for interval (configurable per currency)
                check_interval = 300  # 5 minutes by default
                if deposit_address.currency.code in ['BTC', 'ETH']:
                    check_interval = 600  # 10 minutes for slower chains
                
                time.sleep(check_interval)
                
                # Refresh the deposit address object
                deposit_address.refresh_from_db()
                
                # Stop if monitoring was disabled
                if not deposit_address.is_active:
                    break
                    
            except Exception as e:
                logger.error(f"Error checking deposit address {deposit_address_id}: {str(e)}")
                # Wait longer before retrying after an error
                time.sleep(900)  # 15 minutes
                continue
                
    except Exception as e:
        logger.error(f"Fatal error in deposit monitoring for address {deposit_address_id}: {str(e)}")
        raise

@shared_task
def sync_wallet_balances():
    """
    Periodic task to sync wallet balances with blockchain
    """
    logger.info("Starting wallet balance sync")
    blockchain = BlockchainManager()
    
    # Only sync active wallets with recent activity
    active_wallets = Wallet.objects.filter(
        Q(last_activity__gte=timezone.now() - timedelta(days=7)) |
        Q(balance__gt=0)
    )
    
    for wallet in active_wallets:
        try:
            # Get actual balance from blockchain
            blockchain_balance = blockchain.get_address_balance(
                wallet.currency.code,
                wallet.address
            )
            
            if blockchain_balance is not None:
                blockchain_balance = Decimal(str(blockchain_balance))
                
                # Update if different (with threshold to avoid tiny changes)
                if abs(blockchain_balance - wallet.balance) > Decimal('0.000001'):
                    logger.info(f"Updating balance for wallet {wallet.id} from {wallet.balance} to {blockchain_balance}")
                    wallet.balance = blockchain_balance
                    wallet.save()
                    
        except Exception as e:
            logger.error(f"Error syncing balance for wallet {wallet.id}: {str(e)}")
            continue
    
    logger.info("Completed wallet balance sync")

@shared_task
def monitor_transaction_statuses():
    """
    Check status of pending transactions on blockchain
    """
    logger.info("Starting transaction status monitoring")
    blockchain = BlockchainManager()
    
    # Get transactions that are still pending
    pending_transactions = Transaction.objects.filter(
        status__in=['pending', 'processing'],
        created_at__gte=timezone.now() - timedelta(days=1)
    )
    
    for tx in pending_transactions:
        try:
            if not tx.txid:
                continue
                
            status_info = blockchain.get_transaction_status(
                tx.currency.code,
                tx.txid,
                network=getattr(tx, 'network', None)
            )
            
            if status_info['status'] != tx.status:
                tx.status = status_info['status']
                
                if status_info['status'] == 'completed':
                    tx.completed_at = timezone.now()
                    # For withdrawals, unlock funds if still locked
                    if tx.type == 'withdrawal' and tx.wallet.locked >= tx.amount:
                        tx.wallet.locked -= tx.amount
                        tx.wallet.save()
                
                tx.save()
                logger.info(f"Updated status for transaction {tx.id} to {tx.status}")
                
        except Exception as e:
            logger.error(f"Error checking status for transaction {tx.id}: {str(e)}")
            continue
    
    logger.info("Completed transaction status monitoring")