# zero_x_service.py - Complete 0x.org integration with API key
import asyncio
import logging
import aiohttp
import json
import os
from decimal import Decimal
from typing import Dict, Optional, Any, Tuple
from tenacity import retry, stop_after_attempt, wait_exponential
from web3 import Web3
from eth_account import Account
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class ZeroXService:
    def __init__(self, chain_id: int = 143):
        self.CHAIN_ID = chain_id
        self.API_BASE = "https://api.0x.org"
        
        # Load 0x API key from environment
        self.API_KEY = os.getenv('ZEROX_API_KEY', '')
        if not self.API_KEY:
            logger.warning("⚠️  ZEROX_API_KEY not found in .env - using public API (rate limited)")
        
        # Token addresses - MONAD (correct for Monad chain)
        self.NATIVE_TOKEN = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"  # Native ETH placeholder
        
        # Trading parameters
        self.SLIPPAGE_PERCENTAGE = 1.0  # 1% slippage
        self.DEADLINE_MINUTES = 30
        self.API_TIMEOUT = 30
        self.TX_TIMEOUT = 180  # Transaction timeout in seconds
        
        # Gas settings
        self.DEFAULT_GAS_LIMIT = 300000
        self.PRIORITY_FEE = 1000000000  # 1 gwei
        
        logger.info(f"✅ 0x Service initialized for Monad (chain {chain_id})")
        logger.info(f"🔑 API Key: {'✅ Provided' if self.API_KEY else '❌ Not provided (using public)'}")
        logger.info(f"📊 Slippage: {self.SLIPPAGE_PERCENTAGE}%")
        logger.info(f"⏰ Deadline: {self.DEADLINE_MINUTES} minutes")
    
    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers for 0x API requests"""
        headers = {
            'Content-Type': 'application/json',
            '0x-version': 'v2',
            'User-Agent': 'MonadVolumeBot/1.0'
        }
        
        # Add API key if available
        if self.API_KEY:
            headers['0x-api-key'] = self.API_KEY
            headers['0x-chain-id'] = str(self.CHAIN_ID)
        
        return headers
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def get_swap_quote(
        self,
        sell_token: str,
        buy_token: str,
        sell_amount: Decimal,
        taker_address: str,
        skip_validation: bool = False
    ) -> Optional[Dict]:
        """Get swap quote from 0x.org with API key headers"""
        try:
            # Convert to wei (18 decimals)
            sell_amount_wei = int(sell_amount * Decimal('1e18'))
            
            params = {
                "sellToken": sell_token,
                "buyToken": buy_token,
                "sellAmount": str(sell_amount_wei),
                "takerAddress": taker_address,
                "slippagePercentage": self.SLIPPAGE_PERCENTAGE / 100,
                "deadlineMinutes": self.DEADLINE_MINUTES,
                "chainId": self.CHAIN_ID,
                "skipValidation": "true" if skip_validation else "false",
                "enableSlippageProtection": "true",
                "affiliateAddress": "0x0000000000000000000000000000000000000000",
                "enableRFQT": "false",
                "intentOnFilling": "true"
            }
            
            url = f"{self.API_BASE}/swap/v1/quote"
            
            logger.info(f"📡 Requesting 0x quote: {sell_amount:.6f} MONAD → token")
            
            async with aiohttp.ClientSession(headers=self._get_headers()) as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                ) as response:
                    if response.status == 200:
                        quote = await response.json()
                        
                        # Add human-readable amounts
                        if 'buyAmount' in quote:
                            buy_amount_wei = Decimal(quote['buyAmount'])
                            quote['buyAmountDecimal'] = buy_amount_wei / Decimal('1e18')
                        
                        if 'sellAmount' in quote:
                            sell_amount_wei = Decimal(quote['sellAmount'])
                            quote['sellAmountDecimal'] = sell_amount_wei / Decimal('1e18')
                        
                        # Log quote details
                        logger.info(f"📊 0x Quote received:")
                        logger.info(f"   From: {quote.get('sellAmountDecimal', 0):.6f} MONAD")
                        logger.info(f"   To: {quote.get('buyAmountDecimal', 0):.6f} tokens")
                        
                        if 'estimatedPriceImpact' in quote:
                            price_impact = float(quote['estimatedPriceImpact']) * 100
                            quote['priceImpactPercent'] = price_impact
                            logger.info(f"   Price Impact: {price_impact:.2f}%")
                        
                        if 'gasPrice' in quote:
                            gas_price_gwei = int(quote['gasPrice']) / 1e9
                            logger.info(f"   Gas Price: {gas_price_gwei:.2f} gwei")
                        
                        if 'gas' in quote:
                            logger.info(f"   Gas Estimate: {quote['gas']}")
                        
                        return quote
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ 0x API Error {response.status}")
                        
                        # Log headers for debugging
                        logger.error(f"   Response headers: {dict(response.headers)}")
                        
                        # Try to parse error message
                        try:
                            error_json = json.loads(error_text)
                            logger.error(f"   Error JSON: {json.dumps(error_json, indent=2)}")
                            
                            if 'validationErrors' in error_json:
                                for err in error_json['validationErrors']:
                                    logger.error(f"   Validation error: {err.get('reason', 'Unknown')}")
                            elif 'message' in error_json:
                                logger.error(f"   Message: {error_json['message']}")
                            elif 'detail' in error_json:
                                logger.error(f"   Detail: {error_json['detail']}")
                                
                        except json.JSONDecodeError:
                            logger.error(f"   Raw error: {error_text[:500]}")
                        
                        return None
                        
        except asyncio.TimeoutError:
            logger.error("❌ 0x API timeout")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"❌ HTTP Client error: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error getting 0x quote: {e}")
            return None
    
    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=2, min=3, max=10)
    )
    async def get_price(
        self,
        sell_token: str,
        buy_token: str,
        sell_amount: Decimal
    ) -> Optional[Dict]:
        """Get price quote (no transaction data)"""
        try:
            sell_amount_wei = int(sell_amount * Decimal('1e18'))
            
            params = {
                "sellToken": sell_token,
                "buyToken": buy_token,
                "sellAmount": str(sell_amount_wei),
                "chainId": self.CHAIN_ID
            }
            
            url = f"{self.API_BASE}/swap/v1/price"
            
            async with aiohttp.ClientSession(headers=self._get_headers()) as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                ) as response:
                    if response.status == 200:
                        price_data = await response.json()
                        
                        # Add human-readable amounts
                        if 'buyAmount' in price_data:
                            price_data['buyAmountDecimal'] = Decimal(price_data['buyAmount']) / Decimal('1e18')
                        if 'sellAmount' in price_data:
                            price_data['sellAmountDecimal'] = Decimal(price_data['sellAmount']) / Decimal('1e18')
                        
                        return price_data
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Price API error {response.status}: {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"❌ Error getting price: {e}")
            return None
    
    async def get_token_pairs(self) -> Optional[Dict]:
        """Get available token pairs for the chain"""
        try:
            params = {
                "chainId": self.CHAIN_ID
            }
            
            url = f"{self.API_BASE}/swap/v1/token-pairs"
            
            async with aiohttp.ClientSession(headers=self._get_headers()) as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.API_TIMEOUT)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Token pairs error {response.status}: {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"❌ Error getting token pairs: {e}")
            return None
    
    async def execute_swap_transaction(
        self,
        quote: Dict,
        private_key: str,
        wallet_address: str,
        web3_instance: Web3
    ) -> Dict:
        """Execute swap transaction from 0x quote"""
        try:
            if not quote or 'tx' not in quote:
                return {'success': False, 'error': 'Invalid quote format'}
            
            tx_data = quote['tx']
            
            # Build EIP-1559 transaction
            transaction = {
                'to': tx_data.get('to'),
                'value': int(tx_data.get('value', 0)),
                'data': tx_data.get('data'),
                'gas': int(tx_data.get('gas', self.DEFAULT_GAS_LIMIT)),
                'maxFeePerGas': int(tx_data.get('maxFeePerGas', web3_instance.eth.gas_price)),
                'maxPriorityFeePerGas': int(tx_data.get('maxPriorityFeePerGas', self.PRIORITY_FEE)),
                'chainId': self.CHAIN_ID,
                'type': 2  # EIP-1559
            }
            
            # Get nonce
            transaction['nonce'] = web3_instance.eth.get_transaction_count(wallet_address)
            
            # Validate transaction
            if not transaction['to']:
                return {'success': False, 'error': 'No recipient in transaction'}
            
            # Estimate gas if not provided
            if transaction['gas'] == 0:
                try:
                    estimated_gas = web3_instance.eth.estimate_gas(transaction)
                    transaction['gas'] = int(estimated_gas * 1.2)  # 20% buffer
                    logger.info(f"   Gas estimated: {estimated_gas}, using {transaction['gas']}")
                except Exception as gas_error:
                    logger.warning(f"⚠️ Gas estimation failed: {gas_error}")
                    transaction['gas'] = self.DEFAULT_GAS_LIMIT
            
            # Sign transaction
            signed_txn = web3_instance.eth.account.sign_transaction(transaction, private_key)
            
            # Send transaction
            tx_hash = web3_instance.eth.send_raw_transaction(signed_txn.rawTransaction)
            tx_hash_hex = tx_hash.hex()
            
            logger.info(f"📤 Swap transaction sent: {tx_hash_hex}")
            logger.info(f"   Value: {web3_instance.from_wei(transaction['value'], 'ether'):.6f} MONAD")
            logger.info(f"   Gas: {transaction['gas']}")
            logger.info(f"   Max Fee: {transaction['maxFeePerGas'] / 1e9:.2f} gwei")
            
            # Wait for receipt
            try:
                receipt = web3_instance.eth.wait_for_transaction_receipt(
                    tx_hash,
                    timeout=self.TX_TIMEOUT,
                    poll_latency=3
                )
                
                if receipt.status == 1:
                    gas_cost = receipt.gasUsed * receipt.effectiveGasPrice
                    gas_cost_eth = web3_instance.from_wei(gas_cost, 'ether')
                    
                    logger.info(f"✅ Swap confirmed in block {receipt.blockNumber}")
                    logger.info(f"   Gas used: {receipt.gasUsed}")
                    logger.info(f"   Gas cost: {gas_cost_eth:.6f} MONAD")
                    logger.info(f"   Effective gas price: {receipt.effectiveGasPrice / 1e9:.2f} gwei")
                    
                    return {
                        'success': True,
                        'tx_hash': tx_hash_hex,
                        'block_number': receipt.blockNumber,
                        'gas_used': receipt.gasUsed,
                        'gas_cost': float(gas_cost_eth),
                        'effective_gas_price': receipt.effectiveGasPrice,
                        'buy_amount': float(quote.get('buyAmountDecimal', 0)),
                        'sell_amount': float(quote.get('sellAmountDecimal', 0)),
                        'transaction': {
                            'to': transaction['to'],
                            'value': transaction['value'],
                            'gas': transaction['gas'],
                            'gas_price': transaction['maxFeePerGas']
                        }
                    }
                else:
                    logger.error(f"❌ Swap failed (reverted): {tx_hash_hex}")
                    
                    # Try to get transaction to see what happened
                    try:
                        tx = web3_instance.eth.get_transaction(tx_hash)
                        logger.error(f"   Transaction details: {dict(tx)}")
                    except:
                        pass
                    
                    return {
                        'success': False,
                        'tx_hash': tx_hash_hex,
                        'error': 'Transaction reverted',
                        'block_number': receipt.blockNumber if 'receipt' in locals() else None
                    }
                    
            except Exception as wait_error:
                logger.error(f"❌ Error waiting for receipt: {wait_error}")
                
                # Check if transaction exists on chain
                try:
                    tx = web3_instance.eth.get_transaction(tx_hash)
                    logger.info(f"   Transaction found on chain, block: {tx.blockNumber if tx.blockNumber else 'pending'}")
                except:
                    logger.info(f"   Transaction not found on chain")
                
                return {
                    'success': False,
                    'tx_hash': tx_hash_hex,
                    'error': f'Receipt wait error: {str(wait_error)}'
                }
                
        except ValueError as ve:
            logger.error(f"❌ Transaction validation error: {ve}")
            return {'success': False, 'error': f'Validation: {str(ve)}'}
        except Exception as e:
            logger.error(f"❌ Swap execution error: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    async def execute_buy_sell_cycle(
        self,
        wallet_manager,
        wallet_index: int,
        token_contract: str,
        amount_monad: Decimal
    ) -> Dict:
        """
        Execute complete BUY → SELL cycle for one wallet
        BUY: MONAD → User's Token
        SELL: User's Token → MONAD (IMMEDIATE)
        """
        try:
            # Get wallet details
            wallet = wallet_manager.get_sub_wallet(wallet_index)
            if not wallet:
                return {'success': False, 'error': f'Wallet {wallet_index} not found'}
            
            wallet_address = wallet['address']
            private_key = wallet['private_key']
            
            logger.info(f"🔄 Wallet {wallet_index}: Starting buy-sell cycle for {amount_monad:.6f} MONAD")
            
            # ============================
            # STEP 1: GET TOKEN INFO
            # ============================
            logger.info(f"🔍 Checking token info for {token_contract[:20]}...")
            token_info = await self.get_token_info(token_contract, wallet_manager.w3)
            logger.info(f"   Token: {token_info.get('symbol', 'UNKNOWN')} ({token_info.get('name', 'Unknown')})")
            logger.info(f"   Decimals: {token_info.get('decimals', 18)}")
            
            # ============================
            # STEP 2: GET BUY QUOTE
            # ============================
            logger.info(f"🛒 Getting buy quote...")
            buy_quote = await self.get_swap_quote(
                sell_token=self.NATIVE_TOKEN,    # MONAD (native token)
                buy_token=token_contract,        # User's token
                sell_amount=amount_monad,
                taker_address=wallet_address
            )
            
            if not buy_quote:
                return {
                    'success': False, 
                    'error': 'Failed to get buy quote', 
                    'stage': 'buy',
                    'wallet_index': wallet_index,
                    'token_info': token_info
                }
            
            # Check if quote is valid
            if 'validationErrors' in buy_quote and buy_quote['validationErrors']:
                errors = buy_quote['validationErrors']
                error_msg = ", ".join([e.get('reason', 'Unknown') for e in errors])
                return {
                    'success': False,
                    'error': f'Buy quote validation failed: {error_msg}',
                    'stage': 'buy',
                    'wallet_index': wallet_index
                }
            
            # ============================
            # STEP 3: EXECUTE BUY
            # ============================
            logger.info(f"💸 Executing buy transaction...")
            buy_result = await self.execute_swap_transaction(
                buy_quote,
                private_key,
                wallet_address,
                wallet_manager.w3
            )
            
            if not buy_result['success']:
                return {
                    'success': False,
                    'error': f'Buy transaction failed: {buy_result.get("error")}',
                    'stage': 'buy',
                    'wallet_index': wallet_index,
                    'buy_quote': buy_quote
                }
            
            buy_tx_hash = buy_result['tx_hash']
            estimated_tokens_bought = Decimal(str(buy_result.get('buy_amount', amount_monad)))
            
            logger.info(f"✅ Buy successful: {estimated_tokens_bought:.6f} {token_info.get('symbol', 'tokens')}")
            logger.info(f"   TX: {buy_tx_hash[:20]}...")
            
            # ============================
            # STEP 4: WAIT FOR CONFIRMATION
            # ============================
            logger.info(f"⏳ Waiting for buy confirmation...")
            await asyncio.sleep(8)  # Increased wait time for better confirmation
            
            # ============================
            # STEP 5: CHECK TOKEN BALANCE
            # ============================
            logger.info(f"📊 Checking token balance...")
            token_balance = await self.get_token_balance(token_contract, wallet_address, wallet_manager.w3)
            
            if token_balance < Decimal('0.000001'):
                logger.warning(f"⚠️ Token balance too low: {token_balance:.10f}")
                # Use estimated amount
                tokens_to_sell = estimated_tokens_bought * Decimal('0.99')
            else:
                tokens_to_sell = token_balance * Decimal('0.99')  # 99% of actual balance
            
            logger.info(f"   Token balance: {token_balance:.6f}")
            logger.info(f"   Will sell: {tokens_to_sell:.6f}")
            
            # ============================
            # STEP 6: GET SELL QUOTE
            # ============================
            logger.info(f"💰 Getting sell quote...")
            sell_quote = await self.get_swap_quote(
                sell_token=token_contract,        # User's token
                buy_token=self.NATIVE_TOKEN,      # Back to MONAD
                sell_amount=tokens_to_sell,
                taker_address=wallet_address,
                skip_validation=True  # Skip validation for immediate sell
            )
            
            if not sell_quote:
                return {
                    'success': False, 
                    'error': 'Failed to get sell quote',
                    'stage': 'sell', 
                    'wallet_index': wallet_index,
                    'buy_tx_hash': buy_tx_hash,
                    'tokens_available': float(token_balance)
                }
            
            # ============================
            # STEP 7: EXECUTE SELL
            # ============================
            logger.info(f"💸 Executing sell transaction...")
            sell_result = await self.execute_swap_transaction(
                sell_quote,
                private_key,
                wallet_address,
                wallet_manager.w3
            )
            
            if not sell_result['success']:
                return {
                    'success': False,
                    'error': f'Sell transaction failed: {sell_result.get("error")}',
                    'stage': 'sell',
                    'wallet_index': wallet_index,
                    'buy_tx_hash': buy_tx_hash,
                    'tokens_available': float(token_balance)
                }
            
            sell_tx_hash = sell_result['tx_hash']
            monad_received = Decimal(str(sell_result.get('buy_amount', amount_monad)))
            
            logger.info(f"✅ Sell successful: {monad_received:.6f} MONAD received")
            logger.info(f"   TX: {sell_tx_hash[:20]}...")
            
            # ============================
            # STEP 8: CALCULATE RESULTS
            # ============================
            profit = monad_received - amount_monad
            profit_percentage = (profit / amount_monad) * 100 if amount_monad > 0 else 0
            
            # Calculate fees
            buy_gas_cost = Decimal(str(buy_result.get('gas_cost', 0)))
            sell_gas_cost = Decimal(str(sell_result.get('gas_cost', 0)))
            total_gas_cost = buy_gas_cost + sell_gas_cost
            
            # Net profit after gas
            net_profit = profit - total_gas_cost
            net_profit_percentage = (net_profit / amount_monad) * 100 if amount_monad > 0 else 0
            
            logger.info(f"📈 Cycle results:")
            logger.info(f"   Initial: {amount_monad:.6f} MONAD")
            logger.info(f"   Final: {monad_received:.6f} MONAD")
            logger.info(f"   Gross Profit: {profit:.6f} MONAD ({profit_percentage:+.4f}%)")
            logger.info(f"   Gas Cost: {total_gas_cost:.6f} MONAD")
            logger.info(f"   Net Profit: {net_profit:.6f} MONAD ({net_profit_percentage:+.4f}%)")
            
            # Get final MONAD balance
            final_balance = wallet_manager.get_wallet_balance(wallet_address)
            logger.info(f"   Final wallet balance: {final_balance:.6f} MONAD")
            
            return {
                'success': True,
                'wallet_index': wallet_index,
                'buy_tx_hash': buy_tx_hash,
                'sell_tx_hash': sell_tx_hash,
                'monad_spent': float(amount_monad),
                'monad_received': float(monad_received),
                'tokens_bought': float(estimated_tokens_bought),
                'tokens_sold': float(tokens_to_sell),
                'token_balance_after_buy': float(token_balance),
                'final_monad_balance': float(final_balance),
                'profit': float(profit),
                'net_profit': float(net_profit),
                'profit_percentage': float(profit_percentage),
                'net_profit_percentage': float(net_profit_percentage),
                'buy_gas_cost': float(buy_gas_cost),
                'sell_gas_cost': float(sell_gas_cost),
                'total_gas_cost': float(total_gas_cost),
                'buy_block': buy_result.get('block_number'),
                'sell_block': sell_result.get('block_number'),
                'buy_gas_used': buy_result.get('gas_used'),
                'sell_gas_used': sell_result.get('gas_used'),
                'token_info': token_info,
                'timestamp': datetime.now().isoformat(),
                'cycle_type': 'buy_sell_immediate'
            }
            
        except Exception as e:
            logger.error(f"❌ Buy-sell cycle failed for wallet {wallet_index}: {e}", exc_info=True)
            return {
                'success': False,
                'wallet_index': wallet_index,
                'error': str(e),
                'stage': 'unknown'
            }
    
    # ... (keep all the other methods: check_token_allowance, get_token_balance, etc.)

# Add to your .env file:
"""
# 0x.org API Configuration
ZEROX_API_KEY=your_0x_api_key_here
"""

# Helper function for datetime import
from datetime import datetime

# Ensure all required imports
__all__ = ['ZeroXService']