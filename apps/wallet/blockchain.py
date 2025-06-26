import os
from web3 import Web3
from bitcoin import *
from bitcoin.transaction import *
from dotenv import load_dotenv
from cryptography.fernet import Fernet
import json
import logging
from decimal import Decimal
from web3.exceptions import TransactionNotFound
from web3.middleware import ExtraDataToPOAMiddleware

load_dotenv()

logger = logging.getLogger(__name__)

class BlockchainManager:
    def __init__(self):
        # Initialize with encryption for private keys
        self.encryption_key = os.getenv('ENCRYPTION_KEY')
        if not self.encryption_key:
            raise ValueError("ENCRYPTION_KEY must be set in environment variables")
        self.cipher = Fernet(self.encryption_key.encode())

        # Ethereum configuration
        self.eth_provider = os.getenv('ETH_PROVIDER_URL', 'https://mainnet.infura.io/v3/YOUR_INFURA_KEY')
        self.w3 = Web3(Web3.HTTPProvider(self.eth_provider))
        
        # Inject POA middleware if needed (for networks like BSC)
        if os.getenv('IS_POA_NETWORK', '').lower() == 'true':
            self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        
        # Bitcoin configuration
        self.btc_network = os.getenv('BTC_NETWORK', 'mainnet')
        self.btc_rpc_url = os.getenv('BTC_RPC_URL')
        self.btc_rpc_user = os.getenv('BTC_RPC_USER')
        self.btc_rpc_password = os.getenv('BTC_RPC_PASSWORD')
        
        # Initialize hot wallets with encrypted private keys
        self.hot_wallets = {
            'BTC': self._decrypt_key(os.getenv('BTC_HOT_WALLET_PRIVKEY')),
            'ETH': self._decrypt_key(os.getenv('ETH_HOT_WALLET_PRIVKEY')),
            'USDT_ERC20': self._decrypt_key(os.getenv('USDT_ERC20_HOT_WALLET_PRIVKEY'))
        }
        
        # USDT contract address (mainnet)
        self.usdt_contract_address = '0xdAC17F958D2ee523a2206206994597C13D831ec7'
        self.usdt_abi = json.loads('''[{"constant":false,"inputs":[{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],"name":"transfer","outputs":[],"payable":false,"stateMutability":"nonpayable","type":"function"}]''')
    
    def _encrypt_key(self, privkey):
        """Encrypt a private key for secure storage"""
        return self.cipher.encrypt(privkey.encode()).decode()
    
    def _decrypt_key(self, encrypted_key):
        """Decrypt an encrypted private key"""
        return self.cipher.decrypt(encrypted_key.encode()).decode()
    
    def generate_address(self, currency):
        """Generate a new deposit address for a currency"""
        try:
            if currency == 'BTC':
                priv = random_key()
                pub = privtopub(priv)
                address = pubtoaddr(pub)
                return {
                    'address': address,
                    'privkey': self._encrypt_key(priv),  # Store encrypted
                    'currency': 'BTC'
                }
            elif currency == 'ETH':
                acct = self.w3.eth.account.create()
                return {
                    'address': acct.address,
                    'privkey': self._encrypt_key(acct.key.hex()),
                    'currency': 'ETH'
                }
            else:
                raise ValueError(f"Unsupported currency: {currency}")
        except Exception as e:
            logger.error(f"Error generating {currency} address: {str(e)}")
            raise
    
    def send_transaction(self, currency, to_address, amount):
        """Send cryptocurrency to an external address"""
        try:
            if currency == 'BTC':
                return self._send_btc_transaction(to_address, amount)
            elif currency == 'ETH':
                return self._send_eth_transaction(to_address, amount)
            elif currency == 'USDT_ERC20':
                return self._send_erc20_transaction(to_address, amount)
            else:
                raise ValueError(f"Unsupported currency: {currency}")
        except Exception as e:
            logger.error(f"Error sending {currency} transaction: {str(e)}")
            raise
    
    def _send_btc_transaction(self, to_address, amount):
        """Send Bitcoin transaction"""
        # In production, you would use a Bitcoin node RPC
        # This is a simplified version using python-bitcoinlib
        
        # Get unspent outputs from your hot wallet
        from_address = pubtoaddr(privtopub(self.hot_wallets['BTC']))
        
        # In a real implementation, you would query your Bitcoin node for UTXOs
        # Here we mock the process
        inputs = [{
            'output': 'dummy_tx_hash:0',  # Would be real UTXO in production
            'value': int(amount * 10**8),  # BTC to satoshis
        }]
        
        # Calculate fee (simplified)
        fee = 10000  # 0.0001 BTC fee
        
        # Create transaction
        tx = mktx(
            inputs,
            [
                {'address': to_address, 'value': int(amount * 10**8) - fee},
                {'address': from_address, 'value': fee}  # Change back to sender
            ]
        )
        
        # Sign transaction
        tx = sign(tx, 0, self.hot_wallets['BTC'])
        
        # In production, you would broadcast this via your Bitcoin node
        # For now we return a mock txid
        txid = tx.hash()
        return txid
    
    def _send_eth_transaction(self, to_address, amount):
        """Send Ethereum native transaction"""
        account = self.w3.eth.account.from_key(self.hot_wallets['ETH'])
        
        # Get current gas price
        gas_price = self.w3.eth.gas_price
        
        # Build transaction
        tx = {
            'nonce': self.w3.eth.getTransactionCount(account.address),
            'to': to_address,
            'value': self.w3.toWei(Decimal(amount), 'ether'),
            'gas': 21000,  # Standard gas limit for simple transfers
            'gasPrice': gas_price,
            'chainId': self.w3.eth.chain_id
        }
        
        # Sign and send
        signed_tx = account.sign_transaction(tx)
        tx_hash = self.w3.eth.sendRawTransaction(signed_tx.rawTransaction)
        return tx_hash
    
    def _send_erc20_transaction(self, to_address, amount):
        """Send ERC20 token transaction (USDT)"""
        account = self.w3.eth.account.from_key(self.hot_wallets['USDT_ERC20'])
        contract = self.w3.eth.contract(address=self.usdt_contract_address, abi=self.usdt_abi)
        
        # USDT uses 6 decimals
        token_amount = int(Decimal(amount) * 10**6)
        
        # Build transaction
        tx = contract.functions.transfer(
            to_address,
            token_amount
        ).buildTransaction({
            'chainId': self.w3.eth.chain_id,
            'gas': 100000,  # Higher gas limit for token transfers
            'gasPrice': self.w3.eth.gas_price,
            'nonce': self.w3.eth.getTransactionCount(account.address),
        })
        
        # Sign and send
        signed_tx = account.sign_transaction(tx)
        tx_hash = self.w3.eth.sendRawTransaction(signed_tx.rawTransaction)
        return tx_hash
    
    def get_transaction_status(self, currency, tx_hash):
        """Check transaction confirmation status"""
        try:
            if currency == 'BTC':
                # In production, query your Bitcoin node
                return {'confirmations': 6, 'status': 'confirmed'}  # Mock
            elif currency in ['ETH', 'USDT_ERC20']:
                tx_receipt = self.w3.eth.getTransactionReceipt(tx_hash)
                if tx_receipt is None:
                    return {'confirmations': 0, 'status': 'pending'}
                
                current_block = self.w3.eth.blockNumber
                confirmations = current_block - tx_receipt.blockNumber
                
                return {
                    'confirmations': confirmations,
                    'status': 'confirmed' if confirmations >= 12 else 'pending',
                    'block_number': tx_receipt.blockNumber
                }
            else:
                raise ValueError(f"Unsupported currency: {currency}")
        except TransactionNotFound:
            return {'confirmations': 0, 'status': 'not_found'}
        except Exception as e:
            logger.error(f"Error checking {currency} transaction status: {str(e)}")
            return {'confirmations': 0, 'status': 'error'}
    
    def get_address_balance(self, currency, address):
        """Get current balance of an address"""
        try:
            if currency == 'BTC':
                # In production, query your Bitcoin node
                return 0.0  # Mock value
            elif currency == 'ETH':
                balance_wei = self.w3.eth.getBalance(address)
                return self.w3.fromWei(balance_wei, 'ether')
            elif currency == 'USDT_ERC20':
                contract = self.w3.eth.contract(address=self.usdt_contract_address, abi=self.usdt_abi)
                balance = contract.functions.balanceOf(address).call()
                return balance / 10**6  # USDT has 6 decimals
            else:
                raise ValueError(f"Unsupported currency: {currency}")
        except Exception as e:
            logger.error(f"Error getting {currency} balance: {str(e)}")
            raise
    
    def get_exchange_rate(self, base_currency, quote_currency):
        """Get current exchange rate from an external API"""
        # In production, implement with CoinGecko, Binance, or other API
        # This is a mock implementation
        rates = {
            'BTC_USDT': 50000.00,
            'ETH_USDT': 3000.00,
            'USDT_USD': 1.00
        }
        
        pair = f"{base_currency}_{quote_currency}"
        if pair in rates:
            return rates[pair]
        
        # Try inverse rate
        inverse_pair = f"{quote_currency}_{base_currency}"
        if inverse_pair in rates:
            return 1 / rates[inverse_pair]
        
        return None