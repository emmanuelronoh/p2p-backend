# p2p/utils.py
import json
import time
from decimal import Decimal
from pathlib import Path
from typing import Optional, Tuple

from django.conf import settings
from django.db import transaction
from web3 import Web3
from web3.exceptions import ContractLogicError, TransactionNotFound
from web3.types import TxReceipt
from eth_account import Account
from eth_account.messages import encode_defunct
import hmac
import hashlib

from .models import EscrowWallet, P2PListing, P2PTrade
from .exceptions import (
    EscrowError,
    InsufficientFundsError,
    TransactionFailedError,
    WalletError,
)

# Constants
GAS_LIMIT = 150000
GAS_PRICE = 5  # gwei
POLL_INTERVAL = 15  # seconds
MAX_POLL_ATTEMPTS = 120  # ~30 minutes total
USDT_DECIMALS = 6

# Load ABI
ABI_PATH = Path(__file__).resolve().parent / "abi/usdt.json"
with open(ABI_PATH) as f:
    USDT_ABI = json.load(f)

# Initialize Web3
w3 = Web3(Web3.HTTPProvider(settings.WEB3_RPC_URL))
USDT = w3.eth.contract(address=settings.USDT_ADDR, abi=USDT_ABI)

def generate_user_token(client_token: str) -> str:
    """Generate HMAC-SHA256 user token from client token"""
    hmac_key = settings.XUSDT_SETTINGS['USER_TOKEN_HMAC_KEY'].encode()
    return hmac.new(hmac_key, client_token.encode(), hashlib.sha256).hexdigest()

def _sign_and_send(tx: dict, private_key: str) -> Tuple[str, TxReceipt]:
    """Sign and send a transaction, returning tx hash and receipt."""
    try:
        signed_tx = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction).hex()
        
        # Wait for transaction receipt
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt.status == 0:
            raise TransactionFailedError("Transaction reverted")
            
        return tx_hash, receipt
    except ContractLogicError as e:
        raise EscrowError(f"Contract error: {str(e)}")
    except Exception as e:
        raise EscrowError(f"Transaction failed: {str(e)}")

def create_escrow_wallet() -> EscrowWallet:
    """Create a new escrow wallet with a unique Ethereum address."""
    try:
        acct = w3.eth.account.create()
        return EscrowWallet(address=acct.address)  # Return unsaved instance
    except Exception as e:
        raise WalletError(f"Failed to create escrow wallet: {str(e)}")

def transfer_usdt(from_address: str, to_address: str, amount_wei: int, private_key: str) -> str:
    """
    Transfer USDT between addresses.
    
    Args:
        from_address: Sender address
        to_address: Recipient address
        amount_wei: Amount in USDT wei (6 decimals)
        private_key: Sender's private key
        
    Returns:
        Transaction hash
    """
    try:
        # Build transaction
        tx = USDT.functions.transfer(
            w3.to_checksum_address(to_address),
            amount_wei
        ).build_transaction({
            'from': w3.to_checksum_address(from_address),
            'gas': GAS_LIMIT,
            'gasPrice': w3.to_wei(GAS_PRICE, 'gwei'),
            'nonce': w3.eth.get_transaction_count(from_address),
        })

        # Sign and send
        tx_hash, _ = _sign_and_send(tx, private_key)
        return tx_hash
        
    except Exception as e:
        raise EscrowError(f"USDT transfer failed: {str(e)}")

def fund_escrow(listing: P2PListing, merchant_wallet: str, private_key: str) -> str:
    """
    Fund an escrow wallet for a P2P listing.
    
    Args:
        listing: P2PListing instance
        merchant_wallet: Merchant's wallet address
        private_key: Merchant's private key
        
    Returns:
        Transaction hash
    """
    if not listing.escrow_wallet:
        raise EscrowError("Listing has no escrow wallet")
        
    amount_wei = int(listing.crypto_amount * (10 ** USDT_DECIMALS))
    
    try:
        # Transfer USDT from merchant to escrow
        tx_hash = transfer_usdt(
            from_address=merchant_wallet,
            to_address=listing.escrow_wallet.address,
            amount_wei=amount_wei,
            private_key=private_key
        )
        
        # Verify the transfer was successful
        balance = USDT.functions.balanceOf(listing.escrow_wallet.address).call()
        if balance < amount_wei:
            raise EscrowError("Escrow not funded after transfer")
            
        # Update statuses
        listing.escrow_wallet.mark_as_funded(listing.crypto_amount)
        listing.status = 2  # Funded
        listing.save()
        
        return tx_hash
        
    except Exception as e:
        listing.escrow_wallet.status = 'error'
        listing.escrow_wallet.save()
        raise EscrowError(f"Failed to fund escrow: {str(e)}")

def wait_for_deposit(wallet: EscrowWallet, min_amount: Decimal) -> None:
    """
    Monitor an escrow wallet for incoming deposits.
    
    Args:
        wallet: EscrowWallet instance to monitor
        min_amount: Minimum amount (in USDT) required to consider the wallet funded
        
    Raises:
        EscrowError: If monitoring fails
        TimeoutError: If max polling attempts reached without funding
    """
    min_amount_wei = int(min_amount * (10 ** USDT_DECIMALS))
    
    for attempt in range(MAX_POLL_ATTEMPTS):
        try:
            balance = USDT.functions.balanceOf(wallet.address).call()
            if balance >= min_amount_wei:
                with transaction.atomic():
                    wallet.amount = Decimal(balance) / Decimal(10 ** USDT_DECIMALS)
                    wallet.status = "funded"
                    wallet.save(update_fields=["amount", "status"])
                return
                
            time.sleep(POLL_INTERVAL)
            
        except Exception as e:
            raise EscrowError(f"Failed to check balance: {str(e)}")

    raise TimeoutError("Funding not detected within timeout period")

def release_to(buyer_addr: str, wallet: EscrowWallet, amount: Decimal, fee: Decimal) -> str:
    """
    Release funds from escrow to buyer's address.
    
    Args:
        buyer_addr: Recipient's Ethereum address
        wallet: EscrowWallet instance
        amount: Amount to transfer (in USDT)
        fee: System fee to collect (in USDT)
        
    Returns:
        Transaction hash
        
    Raises:
        InsufficientFundsError: If escrow has insufficient balance
        EscrowError: If transfer fails
    """
    system_wallet = SystemWallet.objects.select_for_update().first()
    if not system_wallet:
        raise WalletError("No system wallet configured")

    # Convert amounts to wei
    amount_wei = int(amount * (10 ** USDT_DECIMALS))
    fee_wei = int(fee * (10 ** USDT_DECIMALS))
    
    try:
        # Check balance first
        balance = USDT.functions.balanceOf(wallet.address).call()
        if balance < amount_wei:
            raise InsufficientFundsError("Escrow has insufficient balance")

        # Prepare and send transaction
        tx = USDT.functions.transfer(
            w3.to_checksum_address(buyer_addr),
            amount_wei
        ).build_transaction({
            'from': system_wallet.address,
            'gas': GAS_LIMIT,
            'gasPrice': w3.to_wei(GAS_PRICE, 'gwei'),
            'nonce': w3.eth.get_transaction_count(system_wallet.address),
        })

        tx_hash, receipt = _sign_and_send(tx, system_wallet.private_key_dec())
        
        # Update records
        with transaction.atomic():
            wallet.status = "released"
            wallet.save(update_fields=["status"])
            
            system_wallet.collected_fees += fee
            system_wallet.save(update_fields=["collected_fees"])
            
        return tx_hash
        
    except Exception as e:
        wallet.status = "error"
        wallet.save(update_fields=["status"])
        raise EscrowError(f"Failed to release funds: {str(e)}")

def check_transaction_status(tx_hash: str) -> Optional[dict]:
    """Check the status of a blockchain transaction."""
    try:
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        if not receipt:
            return None
            
        return {
            'status': 'success' if receipt.status == 1 else 'failed',
            'block_number': receipt.blockNumber,
            'gas_used': receipt.gasUsed,
            'confirmations': w3.eth.block_number - receipt.blockNumber,
        }
    except TransactionNotFound:
        return None
    except Exception as e:
        raise EscrowError(f"Failed to check transaction status: {str(e)}")

def verify_payment_proof(payment_proof: str, expected_hash: str) -> bool:
    """
    Verify a payment proof matches the expected hash.
    
    Args:
        payment_proof: JSON string of payment details
        expected_hash: SHA3-256 hash to verify against
        
    Returns:
        bool: True if verification succeeds
    """
    try:
        proof_hash = hashlib.sha3_256(payment_proof.encode()).hexdigest()
        return proof_hash == expected_hash
    except Exception:
        return False