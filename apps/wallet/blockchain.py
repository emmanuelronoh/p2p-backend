import os
from web3 import Web3, HTTPProvider
from web3.middleware import ExtraDataToPOAMiddleware
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
from dotenv import load_dotenv
from cryptography.fernet import Fernet
import json
import logging
from decimal import Decimal
from web3.exceptions import TransactionNotFound
import requests
from typing import Dict, Optional, Union, List, Any
from eth_utils import to_checksum_address

load_dotenv()

logger = logging.getLogger(__name__)

class BlockchainManager:
    def __init__(self):
        # Initialize encryption
        self.encryption_key = os.getenv('ENCRYPTION_KEY')
        if not self.encryption_key:
            raise ValueError("ENCRYPTION_KEY must be set in environment variables")
        self.cipher = Fernet(self.encryption_key.encode())

        # Initialize supported currencies
        self.supported_currencies = self._get_supported_currencies()
        
        # Ethereum configuration (required for USDT and ETH)
        self.eth_provider = os.getenv('ETH_PROVIDER_URL')
        if not self.eth_provider:
            raise ValueError("ETH_PROVIDER_URL must be set in environment variables")
        
        self.w3 = Web3(HTTPProvider(self.eth_provider))
        if not self.w3.is_connected():
            raise ConnectionError("Failed to connect to Ethereum node")
        
        if os.getenv('IS_POA_NETWORK', '').lower() == 'true':
            self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        
        # Bitcoin configuration (optional)
        self.btc_enabled = 'BTC' in self.supported_currencies
        if self.btc_enabled:
            self.btc_network = os.getenv('BTC_NETWORK', 'mainnet')
            self.btc_rpc_url = os.getenv('BTC_RPC_URL')
            self.btc_rpc_user = os.getenv('BTC_RPC_USER')
            self.btc_rpc_password = os.getenv('BTC_RPC_PASSWORD')
        
        # Initialize hot wallets
        self.hot_wallets = self._initialize_hot_wallets()
        
        # Token configurations (primarily USDT)
        self.token_configs = {
            'USDT': {
                'contract_address': to_checksum_address(os.getenv('USDT_ADDR', '0xdAC17F958D2ee523a2206206994597C13D831ec7')),
                'decimals': 6,
                'abi': self._load_erc20_abi()
            }
        }
        
        # Exchange rate provider
        self.exchange_rate_provider = os.getenv('EXCHANGE_RATE_PROVIDER', 'coingecko')
    
    def _get_supported_currencies(self) -> List[str]:
        """Determine which currencies are supported based on environment config"""
        currencies = []
        if os.getenv('USDT_ERC20_HOT_WALLET_PRIVKEY'):
            currencies.extend(['USDT', 'ETH'])  # ETH needed for gas
        if os.getenv('BTC_HOT_WALLET_PRIVKEY'):
            currencies.append('BTC')
        return currencies
    
    def _initialize_hot_wallets(self) -> Dict[str, str]:
        """Initialize and validate hot wallet private keys"""
        wallets = {}
        
        for currency in self.supported_currencies:
            env_var = f"{currency}_HOT_WALLET_PRIVKEY" if currency != 'USDT' else "USDT_ERC20_HOT_WALLET_PRIVKEY"
            encrypted_privkey = os.getenv(env_var)
            
            if not encrypted_privkey:
                raise ValueError(f"{env_var} must be set in environment variables for {currency}")
            
            try:
                privkey = self._decrypt_key(encrypted_privkey)
                
                if currency in ['ETH', 'USDT']:
                    try:
                        acct = self.w3.eth.account.from_key(privkey)
                        if not self.w3.is_address(acct.address):
                            raise ValueError(f"Invalid {currency} private key")
                        wallets[currency] = privkey
                        logger.info(f"Initialized {currency} wallet: {acct.address}")
                    except Exception as e:
                        raise ValueError(f"Invalid {currency} private key: {str(e)}")
                elif currency == 'BTC':
                    if len(privkey) != 64:
                        raise ValueError("BTC private key must be 64 characters long")
                    wallets[currency] = privkey
                    logger.info("Initialized BTC wallet")
            
            except Exception as e:
                raise ValueError(f"Failed to initialize {currency} wallet: {str(e)}")
        
        return wallets
    
    def _load_erc20_abi(self) -> list:
        """Load standard ERC20 ABI"""
        return [
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function"
            },
            {
                "constant": False,
                "inputs": [
                    {"name": "_to", "type": "address"},
                    {"name": "_value", "type": "uint256"}
                ],
                "name": "transfer",
                "outputs": [{"name": "success", "type": "bool"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "type": "function"
            }
        ]
    
    def _encrypt_key(self, privkey: str) -> str:
        """Encrypt a private key for secure storage"""
        return self.cipher.encrypt(privkey.encode()).decode()
    
    def _decrypt_key(self, encrypted_key: str) -> str:
        """Decrypt an encrypted private key"""
        try:
            return self.cipher.decrypt(encrypted_key.encode()).decode()
        except Exception as e:
            logger.error(f"Decryption failed: {str(e)}")
            raise ValueError("Failed to decrypt private key - check your ENCRYPTION_KEY")

    def verify_wallet_connections(self) -> Dict[str, bool]:
        """Verify connections to all enabled blockchains"""
        status = {}
        
        # Verify Ethereum connection
        status['ethereum'] = self.w3.is_connected()
        
        # Verify USDT contract
        if 'USDT' in self.supported_currencies:
            try:
                contract = self.w3.eth.contract(
                    address=self.token_configs['USDT']['contract_address'],
                    abi=self.token_configs['USDT']['abi']
                )
                contract.functions.decimals().call()
                status['usdt_contract'] = True
            except Exception as e:
                logger.error(f"USDT contract verification failed: {str(e)}")
                status['usdt_contract'] = False
        
        # Verify Bitcoin connection
        if self.btc_enabled:
            try:
                rpc = self._get_btc_rpc()
                rpc.getblockcount()
                status['bitcoin'] = True
            except Exception as e:
                logger.error(f"Bitcoin RPC connection failed: {str(e)}")
                status['bitcoin'] = False
        
        return status
    
    def get_wallet_addresses(self) -> Dict[str, str]:
        """Get addresses of all initialized wallets"""
        addresses = {}
        
        if 'ETH' in self.hot_wallets:
            acct = self.w3.eth.account.from_key(self.hot_wallets['ETH'])
            addresses['eth'] = acct.address
        
        if 'USDT' in self.hot_wallets:
            acct = self.w3.eth.account.from_key(self.hot_wallets['USDT'])
            addresses['usdt'] = acct.address
        
        if self.btc_enabled and 'BTC' in self.hot_wallets:
            try:
                rpc = self._get_btc_rpc()
                addresses['btc'] = rpc.getaccountaddress("")
            except Exception as e:
                logger.error(f"Failed to get BTC address: {str(e)}")
        
        return addresses

    def generate_address(self, currency: str) -> Dict[str, str]:
        """Generate a new deposit address for a currency"""
        try:
            if currency == 'BTC' and self.btc_enabled:
                return self._generate_btc_address()
            elif currency in ['ETH', 'USDT'] and currency in self.supported_currencies:
                return self._generate_eth_address(currency)
            else:
                raise ValueError(f"Unsupported currency: {currency}")
        except Exception as e:
            logger.error(f"Error generating {currency} address: {str(e)}")
            raise
    
    def _generate_btc_address(self) -> Dict[str, str]:
        """Generate a new BTC address"""
        try:
            rpc = self._get_btc_rpc()
            address = rpc.getnewaddress()
            return {
                'address': address,
                'currency': 'BTC',
                'privkey': ''  # Not exposing private key for BTC (handled by node)
            }
        except JSONRPCException as e:
            logger.error(f"BTC RPC error: {str(e)}")
            raise ConnectionError("Failed to generate BTC address")
    
    def _generate_eth_address(self, currency: str) -> Dict[str, str]:
        """Generate a new ETH or token address"""
        acct = self.w3.eth.account.create()
        return {
            'address': acct.address,
            'privkey': self._encrypt_key(acct.key.hex()),
            'currency': currency
        }
    
    def send_transaction(self, currency: str, to_address: str, amount: Union[float, Decimal]) -> str:
        """Send cryptocurrency to an external address"""
        self._validate_transaction_params(currency, to_address, amount)
        
        try:
            if currency == 'BTC' and self.btc_enabled:
                return self._send_btc_transaction(to_address, amount)
            elif currency == 'ETH' and 'ETH' in self.supported_currencies:
                return self._send_eth_transaction(to_address, amount)
            elif currency == 'USDT' and 'USDT' in self.supported_currencies:
                return self._send_erc20_transaction(to_address, amount)
            else:
                raise ValueError(f"Unsupported currency: {currency}")
        except Exception as e:
            logger.error(f"Error sending {currency} transaction: {str(e)}")
            raise
    
    def _validate_transaction_params(self, currency: str, address: str, amount: Union[float, Decimal]):
        """Validate transaction parameters"""
        if not isinstance(amount, (float, Decimal)) or amount <= 0:
            raise ValueError("Amount must be a positive number")
        
        if currency == 'BTC' and self.btc_enabled:
            if not self._validate_btc_address(address):
                raise ValueError("Invalid BTC address")
        elif currency in ['ETH', 'USDT'] and currency in self.supported_currencies:
            if not self.w3.is_address(address):
                raise ValueError("Invalid ETH address")
            # Convert to checksum address
            to_checksum_address(address)
        else:
            raise ValueError(f"Currency {currency} not supported or not configured")
    
    def _validate_btc_address(self, address: str) -> bool:
        """Validate BTC address format"""
        try:
            rpc = self._get_btc_rpc()
            return rpc.validateaddress(address)['isvalid']
        except JSONRPCException:
            return False
    
    def _get_btc_rpc(self) -> AuthServiceProxy:
        """Get authenticated Bitcoin RPC connection"""
        if not all([self.btc_rpc_url, self.btc_rpc_user, self.btc_rpc_password]):
            raise ConnectionError("Bitcoin RPC configuration incomplete")
        
        return AuthServiceProxy(
            f"http://{self.btc_rpc_user}:{self.btc_rpc_password}@{self.btc_rpc_url}"
        )
    
    def _send_btc_transaction(self, to_address: str, amount: Union[float, Decimal]) -> str:
        """Send Bitcoin transaction"""
        try:
            rpc = self._get_btc_rpc()
            
            # Convert amount to BTC (assuming input is in BTC)
            btc_amount = float(amount)
            
            # Send transaction
            txid = rpc.sendtoaddress(to_address, btc_amount)
            
            # Return transaction ID
            return txid
        except JSONRPCException as e:
            logger.error(f"BTC send error: {str(e)}")
            if "Insufficient funds" in str(e):
                raise ValueError("Insufficient BTC balance")
            raise ConnectionError("Failed to send BTC transaction")
    
    def _send_eth_transaction(self, to_address: str, amount: Union[float, Decimal]) -> str:
        """Send Ethereum native transaction"""
        account = self.w3.eth.account.from_key(self.hot_wallets['ETH'])
        
        # Convert amount to wei
        amount_wei = self.w3.to_wei(Decimal(str(amount)), 'ether')
        
        # Get current gas price with buffer
        gas_price = int(self.w3.eth.gas_price * 1.2)  # 20% buffer
        
        # Build transaction
        tx = {
            'nonce': self.w3.eth.get_transaction_count(account.address),
            'to': to_checksum_address(to_address),
            'value': amount_wei,
            'gas': 21000,  # Standard gas limit for simple transfers
            'gasPrice': gas_price,
            'chainId': self.w3.eth.chain_id
        }
        
        # Estimate gas (adjust if needed)
        try:
            tx['gas'] = self.w3.eth.estimate_gas(tx)
        except:
            pass  # Use default if estimation fails
        
        # Sign and send
        try:
            signed_tx = account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            return tx_hash.hex()
        except Exception as e:
            logger.error(f"ETH send error: {str(e)}")
            if "insufficient funds" in str(e).lower():
                raise ValueError("Insufficient ETH balance for transaction")
            raise ConnectionError("Failed to send ETH transaction")
    
    def _send_erc20_transaction(self, to_address: str, amount: Union[float, Decimal]) -> str:
        """Send ERC20 token transaction (USDT)"""
        account = self.w3.eth.account.from_key(self.hot_wallets['USDT'])
        token_config = self.token_configs['USDT']
        
        # Initialize contract
        contract = self.w3.eth.contract(
            address=token_config['contract_address'],
            abi=token_config['abi']
        )
        
        # Convert amount to token units
        token_amount = int(Decimal(str(amount)) * 10 ** token_config['decimals'])
        
        # Build transaction
        tx = contract.functions.transfer(
            to_checksum_address(to_address),
            token_amount
        ).build_transaction({
            'chainId': self.w3.eth.chain_id,
            'gas': 100000,  # Will be adjusted
            'gasPrice': int(self.w3.eth.gas_price * 1.2),  # 20% buffer
            'nonce': self.w3.eth.get_transaction_count(account.address),
        })
        
        # Estimate gas
        try:
            tx['gas'] = contract.functions.transfer(
                to_checksum_address(to_address),
                token_amount
            ).estimate_gas({
                'from': account.address
            })
        except Exception as e:
            logger.warning(f"Gas estimation failed: {str(e)}")
            tx['gas'] = 100000  # Fallback value
        
        # Check ETH balance for gas fees
        eth_balance = self.w3.eth.get_balance(account.address)
        required_eth = tx['gas'] * tx['gasPrice']
        if eth_balance < required_eth:
            raise ValueError("Insufficient ETH for gas fees")
        
        # Sign and send
        try:
            signed_tx = account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            return tx_hash.hex()
        except Exception as e:
            logger.error(f"USDT send error: {str(e)}")
            if "insufficient funds" in str(e).lower():
                raise ValueError("Insufficient USDT balance")
            raise ConnectionError("Failed to send USDT transaction")
    
    def get_transaction_status(self, currency: str, tx_hash: str) -> Dict[str, Union[int, str]]:
        """Check transaction confirmation status"""
        try:
            if currency == 'BTC' and self.btc_enabled:
                return self._get_btc_transaction_status(tx_hash)
            elif currency in ['ETH', 'USDT'] and currency in self.supported_currencies:
                return self._get_eth_transaction_status(tx_hash)
            else:
                raise ValueError(f"Unsupported currency: {currency}")
        except Exception as e:
            logger.error(f"Error checking {currency} transaction status: {str(e)}")
            return {'confirmations': 0, 'status': 'error'}
    
    def _get_btc_transaction_status(self, tx_hash: str) -> Dict[str, Union[int, str]]:
        """Get BTC transaction status"""
        try:
            rpc = self._get_btc_rpc()
            tx = rpc.gettransaction(tx_hash)
            
            if tx['confirmations'] <= 0:
                return {'confirmations': 0, 'status': 'pending'}
            
            return {
                'confirmations': tx['confirmations'],
                'status': 'confirmed',
                'block_number': tx.get('blockheight', None)
            }
        except JSONRPCException as e:
            if "Invalid or non-wallet transaction id" in str(e):
                return {'confirmations': 0, 'status': 'not_found'}
            raise
    
    def _get_eth_transaction_status(self, tx_hash: str) -> Dict[str, Union[int, str]]:
        """Get ETH/USDT transaction status"""
        try:
            tx_receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            if tx_receipt is None:
                # Transaction not yet mined
                tx = self.w3.eth.get_transaction(tx_hash)
                if tx is None:
                    return {'confirmations': 0, 'status': 'not_found'}
                return {'confirmations': 0, 'status': 'pending'}
            
            current_block = self.w3.eth.block_number
            confirmations = current_block - tx_receipt['blockNumber']
            
            if tx_receipt['status'] == 0:
                return {'confirmations': confirmations, 'status': 'failed'}
            
            return {
                'confirmations': confirmations,
                'status': 'confirmed' if confirmations >= 12 else 'pending',
                'block_number': tx_receipt['blockNumber']
            }
        except TransactionNotFound:
            return {'confirmations': 0, 'status': 'not_found'}
    
    def get_address_balance(self, currency: str, address: str) -> Decimal:
        """Get current balance of an address"""
        self._validate_currency(currency)
        
        try:
            if currency == 'BTC' and self.btc_enabled:
                return self._get_btc_balance(address)
            elif currency == 'ETH' and 'ETH' in self.supported_currencies:
                return self._get_eth_balance(address)
            elif currency == 'USDT' and 'USDT' in self.supported_currencies:
                return self._get_erc20_balance(address, 'USDT')
            else:
                raise ValueError(f"Unsupported currency: {currency}")
        except Exception as e:
            logger.error(f"Error getting {currency} balance: {str(e)}")
            raise
    
    def _validate_currency(self, currency: str):
        """Validate currency is supported"""
        if currency not in self.supported_currencies:
            raise ValueError(f"Unsupported currency: {currency}")
    
    def _get_btc_balance(self, address: str) -> Decimal:
        """Get BTC balance for an address"""
        try:
            rpc = self._get_btc_rpc()
            balance = rpc.getreceivedbyaddress(address, 0)  # 0-conf balance
            return Decimal(str(balance))
        except JSONRPCException as e:
            logger.error(f"BTC balance check error: {str(e)}")
            raise ConnectionError("Failed to get BTC balance")
    
    def _get_eth_balance(self, address: str) -> Decimal:
        """Get ETH balance for an address"""
        address = to_checksum_address(address)
        balance_wei = self.w3.eth.get_balance(address)
        return self.w3.from_wei(balance_wei, 'ether')
    
    def _get_erc20_balance(self, address: str, token: str) -> Decimal:
        """Get ERC20 token balance for an address"""
        logger.info(f"Checking {token} balance for address: {address}")
        
        token_config = self.token_configs.get(token)
        if not token_config:
            logger.error(f"Token not configured: {token}")
            raise ValueError(f"Token not configured: {token}")
        
        try:
            contract = self.w3.eth.contract(
                address=token_config['contract_address'],
                abi=token_config['abi']
            )
            
            # Convert address to checksum address
            checksum_address = to_checksum_address(address)
            
            balance = contract.functions.balanceOf(checksum_address).call()
            decimal_balance = Decimal(balance) / (10 ** token_config['decimals'])
            
            logger.info(f"Balance for {address}: {decimal_balance} {token}")
            return decimal_balance
        except Exception as e:
            logger.error(f"Token balance check error for {token}: {str(e)}", exc_info=True)
            raise ConnectionError(f"Failed to get {token} balance")
    
    def get_exchange_rate(self, base_currency: str, quote_currency: str) -> Optional[Decimal]:
        """Get current exchange rate from external API"""
        try:
            if self.exchange_rate_provider == 'coingecko':
                return self._get_coingecko_rate(base_currency, quote_currency)
            else:
                return self._get_binance_rate(base_currency, quote_currency)
        except Exception as e:
            logger.error(f"Error getting exchange rate: {str(e)}")
            return None
    
    def _get_coingecko_rate(self, base: str, quote: str) -> Optional[Decimal]:
        """Get rate from CoinGecko API"""
        coin_ids = {
            'BTC': 'bitcoin',
            'ETH': 'ethereum',
            'USDT': 'tether'
        }
        
        if base not in coin_ids or quote not in coin_ids:
            return None
        
        try:
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {
                'ids': coin_ids[base],
                'vs_currencies': coin_ids[quote]
            }
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            rate = data[coin_ids[base]][coin_ids[quote]]
            return Decimal(str(rate))
        except Exception as e:
            logger.error(f"CoinGecko API error: {str(e)}")
            return None
    
    def _get_binance_rate(self, base: str, quote: str) -> Optional[Decimal]:
        """Get rate from Binance API"""
        symbol = f"{base}{quote}"
        
        try:
            url = "https://api.binance.com/api/v3/ticker/price"
            params = {'symbol': symbol}
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            return Decimal(data['price'])
        except Exception as e:
            logger.error(f"Binance API error: {str(e)}")
            return None
    
    def get_wallet_balance(self, currency: str) -> Decimal:
        """Get balance of our hot wallet"""
        self._validate_currency(currency)
        
        if currency == 'BTC' and self.btc_enabled:
            address = self._get_btc_hot_wallet_address()
            return self._get_btc_balance(address)
        elif currency == 'ETH' and 'ETH' in self.supported_currencies:
            address = self.w3.eth.account.from_key(self.hot_wallets['ETH']).address
            return self._get_eth_balance(address)
        elif currency == 'USDT' and 'USDT' in self.supported_currencies:
            address = self.w3.eth.account.from_key(self.hot_wallets['USDT']).address
            return self._get_erc20_balance(address, 'USDT')
        else:
            raise ValueError(f"Currency {currency} not supported or not configured")
    
    def _get_btc_hot_wallet_address(self) -> str:
        """Get the BTC hot wallet address"""
        try:
            rpc = self._get_btc_rpc()
            return rpc.getaccountaddress("")
        except JSONRPCException as e:
            logger.error(f"BTC wallet address error: {str(e)}")
            raise ConnectionError("Failed to get BTC wallet address")
    
    def get_eth_balance(self, address: str) -> Decimal:
        """Get ETH balance for an address"""
        address = to_checksum_address(address)
        balance_wei = self.w3.eth.get_balance(address)
        return self.w3.from_wei(balance_wei, 'ether')

    def get_btc_balance(self, address: str) -> Decimal:
        """Get BTC balance for an address"""
        try:
            rpc = self._get_btc_rpc()
            balance = rpc.getreceivedbyaddress(address, 0)  # 0-conf balance
            return Decimal(str(balance))
        except JSONRPCException as e:
            logger.error(f"BTC balance check error: {str(e)}")
            raise ConnectionError("Failed to get BTC balance")

    def get_erc20_balance(self, address: str, token: str) -> Decimal:
        """Get ERC20 token balance for an address"""
        return self._get_erc20_balance(address, token)