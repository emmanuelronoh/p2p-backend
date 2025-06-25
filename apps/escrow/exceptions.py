class EscrowError(Exception):
    """Base exception for escrow-related errors"""
    pass

class InsufficientFundsError(EscrowError):
    """Raised when there are insufficient funds for an operation"""
    pass

class TransactionFailedError(EscrowError):
    """Raised when a blockchain transaction fails"""
    pass

class WalletError(EscrowError):
    """Raised for wallet-related errors"""
    pass

class TimeoutError(EscrowError):
    """Raised when an operation times out"""
    pass