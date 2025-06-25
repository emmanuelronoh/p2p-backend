class EscrowError(Exception):
    pass

class InsufficientFundsError(Exception):
    pass

class TransactionFailedError(Exception):
    pass

class WalletError(Exception):
    pass