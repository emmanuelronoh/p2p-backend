from django.core.exceptions import ValidationError
from web3 import Web3

def validate_eth_address(value):
    if not Web3.is_address(value):
        raise ValidationError("Invalid Ethereum address")