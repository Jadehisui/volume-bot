# wallet_manager.py - Sui Implementation with JS bridge
import os
import json
import logging
import subprocess
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from pysui import SuiConfig, SyncClient
from pysui.sui.sui_types.address import SuiAddress
from dotenv import load_dotenv

load_dotenv()

from database import SuiDatabase

logger = logging.getLogger(__name__)

class WalletManager:
    def __init__(self, database: SuiDatabase, rpc_url: Optional[str] = None):
        self.db = database
        # Configuration
        self.rpc_url = os.getenv('RPC_URL', 'https://fullnode.mainnet.sui.io:443')
        
        # Initialize Sui client
        try:
            self.cfg = SuiConfig.user_config(rpc_url=self.rpc_url)
            self.client = SyncClient(self.cfg)
            logger.info(f"✅ Connected to Sui Node at {self.rpc_url}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Sui client: {e}")
            raise
        
        # Load wallets
        self.main_wallet = self._load_main_wallet()
        self.sub_wallets = self._load_sub_wallets()
        self.fee_wallet = os.getenv('FEE_WALLET_ADDRESS', '0x0f02f9894bed1234e6d72fB75F2DdDA1EE047543')
        
        # Configuration matches implementation plan amounts
        self.MIN_DEPOSIT = Decimal('20')  # 20 SUI
        self.FEE_AMOUNT = Decimal('2')    # 2 SUI fee
        
        logger.info(f"💰 Main wallet: {self.main_wallet['address']}")
        logger.info(f"💸 Fee wallet: {self.fee_wallet}")
        logger.info(f"📱 {len(self.sub_wallets)} sub-wallets loaded")
    
    def _get_address_from_key(self, private_key: str) -> str:
        """Use the JS script to securely extract the address from the suiprivkey"""
        try:
            result = subprocess.run(
                ['node', 'getKeyInfo.js', private_key],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Try to parse stdout first - sometimes Node exits with a signal even after printing
            stdout_clean = result.stdout.strip()
            if stdout_clean:
                try:
                    data = json.loads(stdout_clean)
                    if 'address' in data:
                        return data['address']
                    if 'error' in data:
                        raise ValueError(f"Key error: {data['error']}")
                except json.JSONDecodeError:
                    pass # Not valid JSON, continue to error check

            if result.returncode != 0:
                err_msg = result.stderr.strip() or stdout_clean
                logger.error(f"❌ address extraction failed (Code {result.returncode}): {err_msg}")
                raise ValueError(f"Address extraction failed. Error: {err_msg}")
            
            raise ValueError("No address returned from script")
            
        except FileNotFoundError:
            logger.error("❌ 'node' command not found. Please install Node.js on your VPS.")
            raise ValueError("Node.js is not installed. Please run: sudo apt install nodejs npm")
        except Exception as e:
            logger.error(f"❌ Error in _get_address_from_key: {e}")
            raise

    def _load_main_wallet(self) -> Dict:
        """Load main wallet"""
        private_key = os.getenv('MAIN_WALLET_PRIVATE_KEY', '').strip()
        if not private_key:
            raise ValueError("MAIN_WALLET_PRIVATE_KEY is required")
        
        try:
            address = self._get_address_from_key(private_key)
            logger.info(f"✅ Main wallet loaded: {address}")
            return {'address': address, 'private_key': private_key}
        except Exception as e:
            logger.error(f"❌ Invalid MAIN_WALLET_PRIVATE_KEY: {e}")
            raise
    
    def _load_sub_wallets(self) -> List[Dict]:
        """Load sub-wallets from .env if present (optional)"""
        sub_wallets = []
        for i in range(1, 6):
            env_var = f'SUB_WALLET_{i}_PRIVATE_KEY'
            private_key = os.getenv(env_var, '').strip()
            
            if not private_key:
                # No longer raising error, just skipping
                continue
            
            try:
                address = self._get_address_from_key(private_key)
                sub_wallets.append({'index': i, 'address': address, 'private_key': private_key})
                logger.info(f"✅ Sub-wallet {i} loaded: {address}")
            except Exception as e:
                logger.warning(f"⚠️ Could not load {env_var}: {e}")
        return sub_wallets
    
    def get_sub_wallet(self, index: int) -> Optional[Dict]:
        if 1 <= index <= len(self.sub_wallets):
            return self.sub_wallets[index - 1]
        return None
    
    def get_wallet_balance(self, address: str) -> Decimal:
        """Get SUI balance for a wallet using pysui"""
        from pysui.sui.sui_builders.get_builders import GetCoinTypeBalance
        try:
            # Query the balance using the correct builder for this pysui version
            builder = GetCoinTypeBalance(owner=SuiAddress(address))
            res_data = self.client.execute(builder)
            
            if res_data.is_ok():
                balance_mist = res_data.result_data.total_balance
                balance_sui = Decimal(balance_mist) / Decimal('1000000000')
                return balance_sui
            else:
                logger.error(f"❌ RPC Error getting balance for {address}: {res_data.result_data}")
                return Decimal('0')
        except Exception as e:
            logger.error(f"❌ Exception getting SUI balance for {address}: {e}")
            return Decimal('0')

    async def wait_for_deposit(self, address: str, min_balance: Decimal, timeout_mins: int = 10) -> Tuple[bool, Decimal]:
        """Wait for a deposit to arrive at the address"""
        import time
        start_time = time.time()
        timeout_secs = timeout_mins * 60
        
        logger.info(f"⏳ Waiting for {min_balance} SUI at {address}...")
        
        while (time.time() - start_time) < timeout_secs:
            current_balance = self.get_wallet_balance(address)
            if current_balance >= min_balance:
                logger.info(f"✅ Deposit detected! Balance: {current_balance} SUI")
                return True, current_balance
            
            # Wait 15 seconds before next check
            await asyncio.sleep(15)
            
        logger.warning(f"⏰ Timeout reached waiting for deposit at {address}")
        return False, self.get_wallet_balance(address)
    
    def generate_session_wallets(self, session_id: int, count: int = 5) -> list:
        """Dynamically generate N unique sub-wallets via JS bridge and store them in DB"""
        try:
            logger.info(f"🔑 Generating {count} isolated wallets for session {session_id}...")
            result = subprocess.run(
                ['node', 'generate_session_wallets.js', str(count)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if result.returncode != 0:
                err_text = result.stderr.strip() or result.stdout.strip()
                logger.error(f"❌ Failed to generate session wallets: {err_text}")
                return []
                
            # Filter standard output spam if any
            output_lines = result.stdout.strip().split('\n')
            json_line = next(line for line in reversed(output_lines) if line.startswith('{'))
            data = json.loads(json_line)
            
            if data.get('success'):
                wallets = data.get('wallets', [])
                self.db.store_session_wallets(session_id, wallets)
                
                # Securely log keys to logs/wallets.txt for tracing
                try:
                    import datetime
                    os.makedirs('logs', exist_ok=True)
                    with open('logs/wallets.txt', 'a') as f:
                        now = datetime.datetime.now().isoformat()
                        f.write(f"--- SESSION {session_id} - {now} ---\n")
                        for w in wallets:
                            f.write(f"Wallet {w['index']}: {w['address']}\n")
                            f.write(f"Private Key: {w['private_key']}\n")
                            f.write(f"Mnemonic: {w['mnemonic']}\n\n")
                    logger.info(f"📝 Logged {len(wallets)} wallet keys to logs/wallets.txt")
                except Exception as log_e:
                    logger.error(f"❌ Failed to log wallet keys: {log_e}")

                return wallets
                
            else:
                logger.error(f"❌ JS Generator failed: {data.get('error')}")
                return []
                
        except Exception as e:
            logger.error(f"❌ Error generating isolated session wallets: {e}")
            return []

    def process_deposit(self, deposit_amount: Decimal, session_id: int) -> Dict:
        """Process SUI deposit: subtract fee + distribute to 5 wallets"""
        try:
            if deposit_amount < self.MIN_DEPOSIT:
                return {'success': False, 'error': f'Deposit must be at least {self.MIN_DEPOSIT} SUI'}
            
            main_balance = self.get_wallet_balance(self.main_wallet['address'])
            if main_balance < deposit_amount:
                return {'success': False, 'error': f'Main wallet has {main_balance:.4f} SUI, need {deposit_amount} SUI'}
            
            logger.info(f"💰 Processing deposit: {deposit_amount} SUI")
            
            remaining_after_fee = deposit_amount - self.FEE_AMOUNT
            # Just divide float equivalently, round down slightly
            amount_per_wallet = Decimal(str(int((remaining_after_fee / 5) * 1000000000) / 1000000000))
            
            logger.info(f"📊 Fee: {self.FEE_AMOUNT} SUI")
            logger.info(f"📊 Trading amount: {remaining_after_fee} SUI")
            logger.info(f"📤 Per wallet: {amount_per_wallet} SUI")
            
            # Send fee
            fee_result = self._transfer_sui_safe(
                from_wallet=self.main_wallet,
                to_address=self.fee_wallet,
                amount_sui=float(self.FEE_AMOUNT),
                description="Fee"
            )
            
            if not fee_result['success']:
                return {'success': False, 'error': f'Fee failed: {fee_result.get("error")}'}
            
            # Send to all 5 SESSION specific wallets
            distribution_results = []
            successful_wallets = 0
            
            # Fetch isolated wallets from our database!
            session_wallets = self.db.get_session_wallets(session_id)
            if not session_wallets or len(session_wallets) == 0:
                 return {'success': False, 'error': f'No dynamically generated unique wallets found for session {session_id}!'}

            for wallet in session_wallets:
                if amount_per_wallet > Decimal('0.001'):
                    result = self._transfer_sui_safe(
                        from_wallet=self.main_wallet,
                        to_address=wallet['address'],
                        amount_sui=float(amount_per_wallet),
                        description=f"To sub-wallet {wallet['index']}"
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
                'wallets_funded': successful_wallets,
                'total_wallets': 5,
                'fee_result': fee_result,
                'distribution_results': distribution_results
            }
            
        except Exception as e:
            logger.error(f"❌ Deposit processing error: {e}")
            return {'success': False, 'error': str(e)}
    
    def process_variable_deposit(self, deposit_amount: Decimal, session_id: int) -> Dict:
        return self.process_deposit(deposit_amount, session_id)
    
    def _transfer_sui_safe(self, from_wallet: Dict, to_address: str, amount_sui: float, description: str = "") -> Dict:
        """Safe SUI transfer via JS bridge"""
        try:
            if amount_sui <= 0:
                return {'success': False, 'error': 'Amount must be positive'}
            
            private_key = from_wallet['private_key']
            
            logger.info(f"📤 Executing transfer to {to_address}...")
            
            # Call node script
            result = subprocess.run(
                ['node', 'transferSui.js', private_key, to_address, str(amount_sui), description],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if result.returncode != 0:
                err_text = result.stderr.strip() or result.stdout.strip()
                logger.error(f"❌ Transfer failed: {err_text}")
                return {'success': False, 'error': f'Failed: {err_text}', 'description': description}
                
            try:
                # the script logs JSON output
                # find the JSON line if PM2 or something else spammed stdout
                output_lines = result.stdout.strip().split('\n')
                json_line = next(line for line in reversed(output_lines) if line.startswith('{'))
                data = json.loads(json_line)
                
                if data.get('success'):
                    logger.info(f"✅ Transfer confirmed! Digest: {data.get('tx_hash')}")
                    return {
                        'success': True,
                        'tx_hash': data.get('tx_hash'),
                        'amount': amount_sui,
                        'description': description
                    }
                else:
                    logger.error(f"❌ Transfer failed on-chain: {data.get('error')}")
                    return {
                        'success': False,
                        'error': data.get('error'),
                        'description': description
                    }
            except Exception as parse_e:
                logger.error(f"❌ Failed to parse bridge output: {result.stdout.strip()}")
                return {'success': False, 'error': str(parse_e), 'description': description}
                
        except Exception as e:
            logger.error(f"❌ Subprocess error: {e}")
            return {'success': False, 'error': str(e), 'description': description}
    
    def get_all_balances(self) -> Dict:
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
        issues = []
        try:
            logger.info("🔍 Validating Sui wallet setup...")
            
            main_balance = self.get_wallet_balance(self.main_wallet['address'])
            logger.info(f"💰 Main wallet: {main_balance:.6f} SUI")
            
            if self.fee_wallet:
                fee_balance = self.get_wallet_balance(self.fee_wallet)
                logger.info(f"💸 Fee wallet: {fee_balance:.6f} SUI")
            else:
                issues.append("Fee wallet address not set")
            
            for i in range(1, 6):
                wallet = self.get_sub_wallet(i)
                if wallet:
                    balance = self.get_wallet_balance(wallet['address'])
                    logger.info(f"📱 Sub-wallet {i}: {balance:.6f} SUI")
                else:
                    # Optional: only log if we generally expect them
                    pass
                    
            if issues:
                return False, issues
            return True, []
                
        except Exception as e:
            return False, [str(e)]