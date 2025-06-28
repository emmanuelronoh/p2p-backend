from web3 import Web3

# Generate a new Ethereum private key
acct = Web3().eth.account.create()
private_key = acct.key.hex()  # This is your USDT private key (same as ETH)
address = acct.address

print("Private Key:", private_key)
print("Address:", address)
