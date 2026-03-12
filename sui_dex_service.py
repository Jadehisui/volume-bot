# sui_dex_service.py - DEX API logic and Swap Execution
import asyncio
import logging
import aiohttp
import json
import subprocess
from decimal import Decimal
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class SuiDexService:
    def __init__(self):
        # We use a JS process wrapping Cetus SDK
        self.SUI_TOKEN = "0x2::sui::SUI"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def execute_cetus_swap(self, private_key: str, from_token: str, to_token: str, amount: int) -> dict:
        """Call TS script to quote and execute swap via Cetus"""
        try:
            logger.info(f"Executing Cetus Swap: {from_token} -> {to_token} (Amount: {amount})")
            process = await asyncio.create_subprocess_exec(
                'node', 'cetusSwap.js', private_key, from_token, to_token, str(amount),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                err_text = stderr.decode().strip() or stdout.decode().strip()
                logger.error(f"❌ Cetus swap failed: {err_text}")
                return {'success': False, 'error': f'Failed: {err_text}'}
                
            try:
                # Find the JSON output from script
                output_lines = stdout.decode().strip().split('\n')
                json_line = next(line for line in reversed(output_lines) if line.startswith('{'))
                result_data = json.loads(json_line)
                return result_data
            except Exception as e:
                logger.error(f"❌ Failed to parse swap script output: {stdout.decode().strip()}")
                return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"❌ Error invoking Cetus swap script: {e}")
            raise

    async def execute_buy_sell_cycle(self, private_key: str, wallet_index: int, token_contract: str, amount_sui: Decimal) -> dict:
        """
        Execute complete BUY → SELL cycle for one wallet locally using dynamic keys
        BUY: SUI → User's Token
        SELL: User's Token → SUI
        """
        amount_mist = int(amount_sui * Decimal("1000000000"))
        
        result_data = {
            'buy_tx': None,
            'sell_tx': None,
            'token_amount_bought': None,
            'duration_seconds': 0,
            'success': False,
            'error': None
        }
        
        try:
            # --- BUY PHASE ---
            logger.info(f"🔄 W{wallet_index} BUY: Swapping {amount_sui} SUI -> Token via Cetus")
            
            buy_exec = await self.execute_cetus_swap(private_key, self.SUI_TOKEN, token_contract, amount_mist)
            if not buy_exec.get('success'):
                raise ValueError(f"Buy trade failed: {buy_exec.get('error')}")
                
            amount_faucet_out = int(buy_exec.get("amount_out", 0))
            if amount_faucet_out == 0:
                 raise ValueError("Buy swap returned 0 tokens out")
                 
            result_data['buy_tx'] = buy_exec.get('tx_hash')
            result_data['token_amount_bought'] = str(amount_faucet_out)
            result_data['tokens_bought'] = str(amount_faucet_out) # Used in volume engine
            result_data['sui_spent'] = amount_mist / Decimal("1000000000")
            result_data['buy_tx_hash'] = buy_exec.get('tx_hash')
            logger.info(f"✅ W{wallet_index} BUY SUCCESS: {buy_exec.get('tx_hash')}")
            
            # Brief pause for on-chain indexing
            await asyncio.sleep(2)
            
            # --- SELL PHASE ---
            # Now we sell the EXACT amount we bought
            logger.info(f"🔄 W{wallet_index} SELL: Swapping {amount_faucet_out} Token -> SUI via Cetus")
            
            sell_exec = await self.execute_cetus_swap(private_key, token_contract, self.SUI_TOKEN, amount_faucet_out)
            if not sell_exec.get('success'):
                raise ValueError(f"Sell trade failed: {sell_exec.get('error')}")
                
            amount_sui_out = int(sell_exec.get("amount_out", 0))    
            result_data['sell_tx'] = sell_exec.get('tx_hash')
            result_data['success'] = True
            result_data['sui_received'] = amount_sui_out / Decimal("1000000000")
            result_data['tokens_sold'] = str(amount_faucet_out) # Used in volume engine
            result_data['sell_tx_hash'] = sell_exec.get('tx_hash')
            # Calculate SUI loss for this cycle (fees + slippage)
            result_data['profit'] = result_data['sui_received'] - result_data['sui_spent']
            result_data['profit_percentage'] = (result_data['profit'] / result_data['sui_spent']) * 100
            
            logger.info(f"✅ W{wallet_index} SELL SUCCESS: {sell_exec.get('tx_hash')}")
            
            return result_data
            
        except Exception as e:
            logger.error(f"❌ W{wallet_index} Cycle Failed: {str(e)}")
            result_data['error'] = str(e)
            return result_data
