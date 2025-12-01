# wallet_manager.py - Complete with all methods
import os
import logging
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from web3 import Web3
from web3.exceptions import TransactionNotFound, TimeExhausted
from eth_account import Account
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class WalletManager:
    def __init__(self, rpc_url: Optional[str] = None):
        # Configuration
        self.rpc_url = os.getenv('RPC_URL', 'https://rpc.monad.xyz')
        self.chain_id = int(os.getenv('CHAIN_ID', '143'))
        
        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        if not self.w3.is_connected():
            raise ConnectionError(f"❌ Cannot connect to RPC: {self.rpc_url}")
        
        logger.info(f"✅ Connected to {self.rpc_url}, chain ID: {self.chain_id}")
        
        # Load wallets
        self.main_wallet = self._load_main_wallet()
        self.sub_wallets = self._load_sub_wallets()
        self.fee_wallet = os.getenv('FEE_WALLET_ADDRESS', '0x0f02f9894bed1234e6d72fB75F2DdDA1EE047543')
        
        # Validate fee wallet address
        if not self.w3.is_address(self.fee_wallet):
            raise ValueError(f"Invalid fee wallet address: {self.fee_wallet}")
        
        # Configuration
        self.MIN_DEPOSIT = Decimal('2000')
        self.FEE_AMOUNT = Decimal('500')
        
        logger.info(f"💰 Main wallet: {self.main_wallet['address']}")
        logger.info(f"💸 Fee wallet: {self.fee_wallet}")
        logger.info(f"📱 {len(self.sub_wallets)} sub-wallets loaded")
    
    def _load_main_wallet(self) -> Dict:
        """Load main wallet"""
        private_key = os.getenv('MAIN_WALLET_PRIVATE_KEY', '').strip()
        
        if not private_key:
            raise ValueError("MAIN_WALLET_PRIVATE_KEY is required")
        
        # Remove 0x prefix if present
        if private_key.startswith('0x'):
            private_key = private_key[2:]
        
        try:
            account = Account.from_key(private_key)
            logger.info(f"✅ Main wallet loaded: {account.address}")
            
            return {
                'address': account.address,
                'private_key': private_key,
                'account': account
            }
        except Exception as e:
            logger.error(f"❌ Invalid MAIN_WALLET_PRIVATE_KEY: {e}")
            raise
    
    def _load_sub_wallets(self) -> List[Dict]:
        """Load all 5 sub-wallets"""
        sub_wallets = []
        
        for i in range(1, 6):
            env_var = f'SUB_WALLET_{i}_PRIVATE_KEY'
            private_key = os.getenv(env_var, '').strip()
            
            if not private_key:
                raise ValueError(f"{env_var} is required")
            
            # Remove 0x prefix if present
            if private_key.startswith('0x'):
                private_key = private_key[2:]
            
            try:
                account = Account.from_key(private_key)
                
                sub_wallets.append({
                    'index': i,
                    'address': account.address,
                    'private_key': private_key,
                    'account': account
                })
                
                logger.info(f"✅ Sub-wallet {i} loaded: {account.address}")
            except Exception as e:
                logger.error(f"❌ Invalid {env_var}: {e}")
                raise
        
        return sub_wallets
    
    def get_sub_wallet(self, index: int) -> Optional[Dict]:
        """Get sub-wallet by index (1-5)"""
        if 1 <= index <= len(self.sub_wallets):
            return self.sub_wallets[index - 1]
        return None
    
    def get_wallet_balance(self, address: str) -> Decimal:
        """Get MONAD balance for a wallet"""
        try:
            if not self.w3.is_address(address):
                logger.error(f"Invalid address: {address}")
                return Decimal('0')
            
            checksum_address = self.w3.to_checksum_address(address)
            balance_wei = self.w3.eth.get_balance(checksum_address)
            balance_eth = self.w3.from_wei(balance_wei, 'ether')
            return Decimal(str(balance_eth))
        except Exception as e:
            logger.error(f"❌ Error getting balance for {address}: {e}")
            return Decimal('0')
    
    def process_deposit(self, deposit_amount: Decimal) -> Dict:
        """
        Process deposit: 500 fee + distribute to 5 wallets
        """
        try:
            # Validate
            if deposit_amount < self.MIN_DEPOSIT:
                return {
                    'success': False,
                    'error': f'Deposit must be at least {self.MIN_DEPOSIT} MONAD'
                }
            
            # Check main wallet balance
            main_balance = self.get_wallet_balance(self.main_wallet['address'])
            if main_balance < deposit_amount:
                return {
                    'success': False,
                    'error': f'Main wallet has {main_balance:.2f} MONAD, need {deposit_amount} MONAD'
                }
            
            logger.info(f"💰 Processing deposit: {deposit_amount} MONAD")
            
            # Calculate amounts
            remaining_after_fee = deposit_amount - self.FEE_AMOUNT
            amount_per_wallet = remaining_after_fee // 5
            remainder = remaining_after_fee % 5
            
            logger.info(f"📊 Fee: {self.FEE_AMOUNT} MONAD")
            logger.info(f"📊 Trading amount: {remaining_after_fee} MONAD")
            logger.info(f"📤 Per wallet: {amount_per_wallet} MONAD")
            logger.info(f"💼 Remainder: {remainder} MONAD")
            
            # Send fee
            fee_result = self._transfer_monad_safe(
                from_wallet=self.main_wallet,
                to_address=self.fee_wallet,
                amount_monad=float(self.FEE_AMOUNT),
                description="Fee"
            )
            
            if not fee_result['success']:
                return {'success': False, 'error': f'Fee failed: {fee_result.get("error")}'}
            
            # Send to all 5 wallets
            distribution_results = []
            successful_wallets = 0
            
            for wallet in self.sub_wallets:
                if amount_per_wallet > Decimal('0'):
                    result = self._transfer_monad_safe(
                        from_wallet=self.main_wallet,
                        to_address=wallet['address'],
                        amount_monad=float(amount_per_wallet),
                        description=f"To wallet {wallet['index']}"
                    )
                    
                    result['wallet_index'] = wallet['index']
                    distribution_results.append(result)
                    
                    if result['success']:
                        successful_wallets += 1
            
            return {
                'success': successful_wallets == 5,
                'deposit_amount': float(deposit_amount),
                'fee_amount': float(self.FEE_AMOUNT),
                'trading_amount': float(remaining_after_fee),
                'amount_per_wallet': float(amount_per_wallet),
                'remainder': float(remainder),
                'wallets_funded': successful_wallets,
                'total_wallets': 5,
                'fee_result': fee_result,
                'distribution_results': distribution_results
            }
            
        except Exception as e:
            logger.error(f"❌ Deposit processing error: {e}")
            return {'success': False, 'error': str(e)}
    
    def process_variable_deposit(self, deposit_amount: Decimal) -> Dict:
        """Process ANY deposit amount (2000+ MONAD) - same as process_deposit"""
        return self.process_deposit(deposit_amount)
    
    def _transfer_monad_safe(self, from_wallet: Dict, to_address: str, amount_monad: float, description: str = "") -> Dict:
        """Safe MONAD transfer"""
        try:
            if amount_monad <= 0:
                return {'success': False, 'error': 'Amount must be positive'}
            
            if not self.w3.is_address(to_address):
                return {'success': False, 'error': f'Invalid to address: {to_address}'}
            
            from_address = from_wallet['address']
            private_key = from_wallet['private_key']
            
            # Get nonce
            nonce = self.w3.eth.get_transaction_count(from_address)
            
            # Build transaction
            transaction = {
                'nonce': nonce,
                'to': self.w3.to_checksum_address(to_address),
                'value': self.w3.to_wei(amount_monad, 'ether'),
                'gas': 21000,
                'gasPrice': self.w3.eth.gas_price,
                'chainId': self.chain_id
            }
            
            # Check balance
            total_cost = transaction['value'] + (transaction['gas'] * transaction['gasPrice'])
            balance_wei = self.w3.eth.get_balance(from_address)
            
            if balance_wei < total_cost:
                needed = self.w3.from_wei(total_cost, 'ether')
                has = self.w3.from_wei(balance_wei, 'ether')
                return {
                    'success': False,
                    'error': f'Insufficient balance. Need {needed:.6f} MONAD, have {has:.6f} MONAD'
                }
            
            # Sign and send
            signed_txn = self.w3.eth.account.sign_transaction(transaction, private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            tx_hash_hex = tx_hash.hex()
            
            logger.info(f"📤 Transaction sent: {tx_hash_hex}")
            
            # Wait for receipt
            try:
                receipt = self.w3.eth.wait_for_transaction_receipt(
                    tx_hash,
                    timeout=120,
                    poll_latency=2
                )
                
                if receipt.status == 1:
                    logger.info(f"✅ Transaction confirmed in block {receipt.blockNumber}")
                    return {
                        'success': True,
                        'tx_hash': tx_hash_hex,
                        'amount': amount_monad,
                        'block_number': receipt.blockNumber,
                        'gas_used': receipt.gasUsed,
                        'description': description
                    }
                else:
                    logger.error(f"❌ Transaction failed (status 0)")
                    return {
                        'success': False,
                        'tx_hash': tx_hash_hex,
                        'error': 'Transaction failed on-chain',
                        'block_number': receipt.blockNumber
                    }
                    
            except TimeExhausted:
                logger.error(f"❌ Transaction timeout")
                return {
                    'success': False,
                    'tx_hash': tx_hash_hex,
                    'error': 'Transaction timeout',
                    'description': description
                }
                
        except Exception as e:
            logger.error(f"❌ Transfer error: {e}")
            return {'success': False, 'error': str(e), 'description': description}
    
    def get_all_balances(self) -> Dict:
        """Get all wallet balances"""
        try:
            balances = {
                'main_wallet': {
                    'address': self.main_wallet['address'],
                    'balance': float(self.get_wallet_balance(self.main_wallet['address']))
                },
                'fee_wallet': {
                    'address': self.fee_wallet,
                    'balance': float(self.get_wallet_balance(self.fee_wallet))
                },
                'sub_wallets': []
            }
            
            for wallet in self.sub_wallets:
                balance = self.get_wallet_balance(wallet['address'])
                balances['sub_wallets'].append({
                    'index': wallet['index'],
                    'address': wallet['address'],
                    'balance': float(balance)
                })
            
            return balances
            
        except Exception as e:
            logger.error(f"❌ Error getting balances: {e}")
            return {}
    
    def validate_wallet_setup(self) -> Tuple[bool, List[str]]:
        """Validate wallet setup - FIXED VERSION"""
        issues = []
        
        try:
            logger.info("🔍 Validating wallet setup...")
            
            # Check main wallet
            main_balance = self.get_wallet_balance(self.main_wallet['address'])
            logger.info(f"💰 Main wallet: {main_balance:.6f} MONAD")
            
            # Check fee wallet
            if self.fee_wallet:
                fee_balance = self.get_wallet_balance(self.fee_wallet)
                logger.info(f"💸 Fee wallet: {fee_balance:.6f} MONAD")
            else:
                issues.append("Fee wallet address not set")
            
            # Check sub-wallets
            for i in range(1, 6):
                wallet = self.get_sub_wallet(i)
                if wallet:
                    balance = self.get_wallet_balance(wallet['address'])
                    logger.info(f"📱 Wallet {i}: {balance:.6f} MONAD")
                else:
                    issues.append(f"Wallet {i} not loaded")
            
            # Check RPC
            try:
                block = self.w3.eth.block_number
                logger.info(f"📦 Current block: {block}")
            except Exception as e:
                issues.append(f"RPC error: {e}")
            
            if issues:
                logger.warning(f"⚠️ Found issues: {issues}")
                return False, issues
            else:
                logger.info("✅ Wallet setup validated")
                return True, []
                
        except Exception as e:
            logger.error(f"❌ Validation error: {e}")
            return False, [f"Validation error: {str(e)}"]