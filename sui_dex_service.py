# sui_dex_service.py - DEX API logic and Swap Execution
import asyncio
import logging
import json
from decimal import Decimal
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class SuiDexService:
    def __init__(self):
        self.SUI_TOKEN = "0x2::sui::SUI"

    # ─────────────────────────────────────────────────────────────────────────
    # CETUS (graduated tokens on DEX)
    # ─────────────────────────────────────────────────────────────────────────
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
                output_lines = stdout.decode().strip().split('\n')
                json_line = next(line for line in reversed(output_lines) if line.startswith('{'))
                return json.loads(json_line)
            except Exception as e:
                logger.error(f"❌ Failed to parse swap script output: {stdout.decode().strip()}")
                return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"❌ Error invoking Cetus swap script: {e}")
            raise

    # ─────────────────────────────────────────────────────────────────────────
    # HOP PRE-BOND (bonding curve — tokens not yet graduated)
    # ─────────────────────────────────────────────────────────────────────────
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def execute_hop_prebond_buy(self, private_key: str, curve_id: str, coin_type: str, amount_mist: int) -> dict:
        """Call hopLaunchBuy.js to buy on the Hop bonding curve"""
        try:
            logger.info(f"Executing Hop Pre-Bond BUY: {coin_type} (Amount: {amount_mist} MIST)")
            process = await asyncio.create_subprocess_exec(
                'node', 'hopLaunchBuy.js', private_key, curve_id, coin_type, str(amount_mist),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                err_text = stderr.decode().strip() or stdout.decode().strip()
                logger.error(f"❌ Hop buy failed: {err_text}")
                return {'success': False, 'error': f'Failed: {err_text}'}

            try:
                output_lines = stdout.decode().strip().split('\n')
                json_line = next(line for line in reversed(output_lines) if line.startswith('{'))
                return json.loads(json_line)
            except Exception as e:
                logger.error(f"❌ Failed to parse Hop buy output: {stdout.decode().strip()}")
                return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"❌ Error invoking hopLaunchBuy.js: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def execute_hop_prebond_sell(self, private_key: str, curve_id: str, coin_type: str, token_amount: int) -> dict:
        """Call hopLaunchSell.js to sell tokens on the Hop bonding curve"""
        try:
            logger.info(f"Executing Hop Pre-Bond SELL: {coin_type} (Amount: {token_amount})")
            process = await asyncio.create_subprocess_exec(
                'node', 'hopLaunchSell.js', private_key, curve_id, coin_type, str(token_amount),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                err_text = stderr.decode().strip() or stdout.decode().strip()
                logger.error(f"❌ Hop sell failed: {err_text}")
                return {'success': False, 'error': f'Failed: {err_text}'}

            try:
                output_lines = stdout.decode().strip().split('\n')
                json_line = next(line for line in reversed(output_lines) if line.startswith('{'))
                return json.loads(json_line)
            except Exception as e:
                logger.error(f"❌ Failed to parse Hop sell output: {stdout.decode().strip()}")
                return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"❌ Error invoking hopLaunchSell.js: {e}")
            raise

    # ─────────────────────────────────────────────────────────────────────────
    # UNIFIED BUY → SELL CYCLE (branches on mode)
    # ─────────────────────────────────────────────────────────────────────────
    async def execute_buy_sell_cycle(
        self,
        private_key: str,
        wallet_index: int,
        token_contract: str,
        amount_sui: Decimal,
        mode: str = 'cetus',
        curve_id: str = None,
    ) -> dict:
        """
        Execute complete BUY → SELL cycle for one wallet.
        mode='cetus'       → both legs go through Cetus DEX aggregator
        mode='hop_prebond' → both legs go through Hop bonding curve
        """
        amount_mist = int(amount_sui * Decimal("1000000000"))

        result_data = {
            'buy_tx': None,
            'sell_tx': None,
            'token_amount_bought': None,
            'duration_seconds': 0,
            'success': False,
            'error': None,
            'wallet_index': wallet_index,
        }

        try:
            if mode == 'hop_prebond':
                # ── HOP PRE-BOND CYCLE ───────────────────────────────────────
                if not curve_id:
                    raise ValueError("curve_id is required for hop_prebond mode")

                logger.info(f"🔄 W{wallet_index} [HOP] BUY: {amount_sui} SUI → {token_contract[:20]}...")
                buy_exec = await self.execute_hop_prebond_buy(private_key, curve_id, token_contract, amount_mist)
                if not buy_exec.get('success'):
                    raise ValueError(f"Hop buy failed: {buy_exec.get('error')}")

                tokens_out = int(buy_exec.get('amount_out', 0))
                if tokens_out == 0:
                    raise ValueError("Hop buy returned 0 tokens out")

                result_data['buy_tx']              = buy_exec.get('tx_hash')
                result_data['buy_tx_hash']         = buy_exec.get('tx_hash')
                result_data['token_amount_bought'] = str(tokens_out)
                result_data['tokens_bought']       = str(tokens_out)
                result_data['sui_spent']           = amount_mist / Decimal("1000000000")
                logger.info(f"✅ W{wallet_index} [HOP] BUY: {buy_exec.get('tx_hash')}")

                await asyncio.sleep(2)

                logger.info(f"🔄 W{wallet_index} [HOP] SELL: {tokens_out} tokens → SUI")
                sell_exec = await self.execute_hop_prebond_sell(private_key, curve_id, token_contract, tokens_out)
                if not sell_exec.get('success'):
                    raise ValueError(f"Hop sell failed: {sell_exec.get('error')}")

                sui_out = int(sell_exec.get('sui_received', 0))
                result_data['sell_tx']           = sell_exec.get('tx_hash')
                result_data['sell_tx_hash']      = sell_exec.get('tx_hash')
                result_data['success']           = True
                result_data['sui_received']      = sui_out / Decimal("1000000000")
                result_data['tokens_sold']       = str(tokens_out)
                result_data['profit']            = result_data['sui_received'] - result_data['sui_spent']
                result_data['profit_percentage'] = (result_data['profit'] / result_data['sui_spent']) * 100
                logger.info(f"✅ W{wallet_index} [HOP] SELL: {sell_exec.get('tx_hash')}")

            else:
                # ── CETUS CYCLE (default) ────────────────────────────────────
                logger.info(f"🔄 W{wallet_index} [CETUS] BUY: {amount_sui} SUI → {token_contract[:20]}...")
                buy_exec = await self.execute_cetus_swap(private_key, self.SUI_TOKEN, token_contract, amount_mist)
                if not buy_exec.get('success'):
                    raise ValueError(f"Buy trade failed: {buy_exec.get('error')}")

                amount_faucet_out = int(buy_exec.get("amount_out", 0))
                if amount_faucet_out == 0:
                    raise ValueError("Buy swap returned 0 tokens out")

                result_data['buy_tx']              = buy_exec.get('tx_hash')
                result_data['buy_tx_hash']         = buy_exec.get('tx_hash')
                result_data['token_amount_bought'] = str(amount_faucet_out)
                result_data['tokens_bought']       = str(amount_faucet_out)
                result_data['sui_spent']           = amount_mist / Decimal("1000000000")
                logger.info(f"✅ W{wallet_index} [CETUS] BUY: {buy_exec.get('tx_hash')}")

                await asyncio.sleep(2)

                logger.info(f"🔄 W{wallet_index} [CETUS] SELL: {amount_faucet_out} tokens → SUI")
                sell_exec = await self.execute_cetus_swap(private_key, token_contract, self.SUI_TOKEN, amount_faucet_out)
                if not sell_exec.get('success'):
                    raise ValueError(f"Sell trade failed: {sell_exec.get('error')}")

                amount_sui_out = int(sell_exec.get("amount_out", 0))
                result_data['sell_tx']           = sell_exec.get('tx_hash')
                result_data['sell_tx_hash']      = sell_exec.get('tx_hash')
                result_data['success']           = True
                result_data['sui_received']      = amount_sui_out / Decimal("1000000000")
                result_data['tokens_sold']       = str(amount_faucet_out)
                result_data['profit']            = result_data['sui_received'] - result_data['sui_spent']
                result_data['profit_percentage'] = (result_data['profit'] / result_data['sui_spent']) * 100
                logger.info(f"✅ W{wallet_index} [CETUS] SELL: {sell_exec.get('tx_hash')}")

            return result_data

        except Exception as e:
            logger.error(f"❌ W{wallet_index} [{mode.upper()}] Cycle Failed: {str(e)}")
            result_data['error'] = str(e)
            return result_data
