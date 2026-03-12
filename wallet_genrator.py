from web3 import Web3
import secrets

def generate_wallets(count=6):
    """
    Generate cryptographically secure Ethereum-compatible wallets
    These should work with Monad blockchain since it's EVM-compatible
    """
    w3 = Web3()
    wallets = []
    
    for i in range(count):
        # Generate a random entropy (extra security layer)
        entropy = secrets.token_hex(32)
        
        # Create account with web3 (uses cryptographically secure RNG)
        account = w3.eth.account.create(entropy)
        
        wallets.append({
            'wallet_number': i + 1,
            'address': account.address,
            'private_key': account.key.hex(),
            'checksum_address': w3.to_checksum_address(account.address)
        })
    
    return wallets

def main():
    print("=" * 80)
    print("Generating 6 Ethereum-compatible Wallets for Monad")
    print("=" * 80)
    print("⚠️  IMPORTANT SECURITY WARNINGS:")
    print("⚠️  These private keys are for educational/testing purposes only")
    print("⚠️  Do not use these wallets for real funds on mainnet")
    print("⚠️  Never share private keys with anyone")
    print("⚠️  Store private keys securely and never commit to version control")
    print("=" * 80)
    print()
    
    wallets = generate_wallets(6)
    
    for wallet in wallets:
        print(f"Wallet #{wallet['wallet_number']}:")
        print(f"Address: {wallet['address']}")
        print(f"Checksum Address: {wallet['checksum_address']}")
        print(f"Private Key: {wallet['private_key']}")
        print("-" * 80)
    
    print("\n✅ Generated 6 wallets successfully!")
    print("\n📝 Next steps for Monad development:")
    print("1. Use these on Monad testnet first")
    print("2. Fund with testnet MONAD tokens")
    print("3. Test transactions before mainnet use")
    print("4. Consider using hardware wallets for large amounts")

if __name__ == "__main__":
    main()