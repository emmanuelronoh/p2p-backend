# wallet/management/commands/check_deposits.py
from django.core.management.base import BaseCommand
from wallet.models import DepositAddress
from wallet.blockchain import BlockchainManager

class Command(BaseCommand):
    help = 'Checks for new deposits on all addresses'
    
    def handle(self, *args, **options):
        blockchain = BlockchainManager()
        addresses = DepositAddress.objects.filter(is_active=True)
        
        for address in addresses:
            balance = address.get_balance()
            if balance > 0:
                # Create deposit transaction
                # Update wallet balance
                self.stdout.write(f'New deposit detected: {balance} {address.currency.code}')