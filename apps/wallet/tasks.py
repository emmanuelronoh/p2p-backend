from celery import shared_task
from .blockchain import BlockchainManager
from .models import Transaction, DepositAddress
import time

@shared_task
def process_withdrawal(transaction_id):
    transaction = Transaction.objects.get(id=transaction_id)
    blockchain = BlockchainManager()
    
    try:
        tx_hash = blockchain.send_transaction(
            transaction.currency.code,
            transaction.address,
            transaction.amount
        )
        
        if tx_hash:
            transaction.status = 'completed'
            transaction.txid = tx_hash.hex()
            transaction.wallet.locked -= transaction.amount
            transaction.wallet.save()
        else:
            transaction.status = 'failed'
            # Return the funds to available balance
            transaction.wallet.locked -= transaction.amount
            transaction.wallet.balance += transaction.amount
            transaction.wallet.save()
            
        transaction.save()
    except Exception as e:
        transaction.status = 'failed'
        transaction.save()
        raise e

@shared_task
def check_deposit_status(deposit_address_id):
    deposit_address = DepositAddress.objects.get(id=deposit_address_id)
    blockchain = BlockchainManager()
    
    while deposit_address.is_active:
        balance = blockchain.get_address_balance(
            deposit_address.currency.code,
            deposit_address.address
        )
        
        if balance > 0:
            # Create deposit transaction
            wallet, _ = Wallet.objects.get_or_create(
                user=deposit_address.user,
                currency=deposit_address.currency,
                defaults={'balance': 0, 'locked': 0}
            )
            
            wallet.balance += balance
            wallet.save()
            
            Transaction.objects.create(
                user=deposit_address.user,
                wallet=wallet,
                currency=deposit_address.currency,
                amount=balance,
                type='deposit',
                status='completed',
                address=deposit_address.address
            )
            
            # Stop monitoring if one-time address
            deposit_address.is_active = False
            deposit_address.save()
            break
        
        time.sleep(300)  # Check every 5 minutes