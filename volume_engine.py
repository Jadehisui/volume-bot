# volume_engine.py - COMPLETE Volume Generation with 70% Swaps
import asyncio
import logging
from decimal import Decimal, ROUND_DOWN
from datetime import datetime, timedelta
import json
from typing import Dict, List, Optional, Tuple

from database import SuiDatabase
from wallet_manager import WalletManager
from sui_dex_service import SuiDexService

logger = logging.getLogger(__name__)

class VolumeEngine:
    """Engine that handles BUY → IMMEDIATE SELL swaps on user's token for all 5 wallets"""
    
    def __init__(self, database: SuiDatabase, wallet_manager: WalletManager):
        self.db = database
        self.wm = wallet_manager
        # Initialize Sui DEX service instead of 0x
        self.dex = SuiDexService()
        
        # Trading parameters - 70% PER TRADE (EXTREME)
        self.TRADING_INTERVAL = 60  # 1 minute between cycles
        self.SESSION_DURATION = 4 * 60 * 60  # 4 hours in seconds
        self.TRADE_PERCENTAGE = Decimal('0.70')  # 70% of current balance per trade!
        self.MIN_TRADE_AMOUNT = Decimal('0.1')   # Minimum trade amount
        self.MAX_CONSECUTIVE_FAILURES = 5        # Stop after this many failures
        
        # Active sessions tracking
        self.active_sessions = {}
        self.running_tasks = {}
        
        logger.warning(f"⚠️  WARNING: Trading at {self.TRADE_PERCENTAGE*100}% per trade - HIGH RISK!")
        logger.info("✅ Volume Engine initialized - Handles BUY→SELL on all 5 wallets")

    async def start_volume_session(self, session_id: int, token_contract: str, deposit_amount: Decimal):
        """
        Start volume generation for a user's token contract
        deposit_amount: Total amount user deposited (2000+ SUI)
        """
        try:
            # Get session details
            session = self.db.get_session_for_trading(session_id)
            if not session:
                logger.error(f"❌ Session {session_id} not found")
                return False
            
            user_id = session[1]
            
            # Calculate trading amount 
            fee_amount = self.wm.FEE_AMOUNT
            trading_amount = deposit_amount - fee_amount
            
            # Calculate amount per wallet (divide by 5, remainder stays)
            amount_per_wallet = trading_amount // 5
            remainder = trading_amount % 5
            
            logger.info("=" * 70)
            logger.info(f"🚀 STARTING VOLUME SESSION #{session_id}")
            logger.info(f"👤 User: {user_id}")
            logger.info(f"📝 Token: {token_contract[:20]}...")
            logger.info(f"💰 Deposit: {deposit_amount} SUI")
            logger.info(f"💸 Fee: {fee_amount} SUI")
            logger.info(f"📊 Trading amount: {trading_amount} SUI")
            logger.info(f"📤 Per wallet: {amount_per_wallet} SUI")
            logger.info(f"💼 Remainder: {remainder} SUI stays in main")
            logger.info(f"⚡ Trade percentage: {self.TRADE_PERCENTAGE*100}% per cycle")
            logger.info(f"⏰ Duration: 4 hours")
            logger.info("=" * 70)
            
            # CHECK FOR EXISTING WALLETS FIRST (they should have been generated in bot.py)
            session_wallets = self.db.get_session_wallets(session_id)
            
            if not session_wallets:
                logger.info(f"🔑 No wallets found for session {session_id}, generating now...")
                # GENERATE ISOLATED WALLETS FOR THIS SESSION! (Fallback)
                session_wallets = self.wm.generate_session_wallets(session_id, count=5)
                
            if not session_wallets or len(session_wallets) != 5:
                logger.error(f"❌ Failed to securely generate or retrieve 5 isolated wallets for session {session_id}")
                return False
                
            # Get initial wallet balances
            initial_balances = {}
            for wallet in session_wallets:
                wallet_index = wallet['index']
                balance = self.wm.get_wallet_balance(wallet['address'])
                initial_balances[wallet_index] = balance
                logger.info(f"💰 Wallet {wallet_index}: {balance:.6f} SUI")
            
            # Store session data
            session_data = {
                'user_id': user_id,
                'token_contract': token_contract,
                'deposit_amount': deposit_amount,
                'fee_amount': fee_amount,
                'trading_amount': trading_amount,
                'initial_per_wallet': amount_per_wallet,
                'remainder': remainder,
                'initial_balances': initial_balances,
                'current_balances': initial_balances.copy(),
                'start_time': datetime.now(),
                'end_time': datetime.now() + timedelta(seconds=self.SESSION_DURATION),
                'cycles_completed': 0,
                'total_trades': 0,
                'total_volume': Decimal('0'),
                'total_profit': Decimal('0'),
                'total_buy_volume': Decimal('0'),
                'total_sell_volume': Decimal('0'),
                'wallets': [1, 2, 3, 4, 5],  # All 5 wallets
                'active_wallets': [1, 2, 3, 4, 5],  # Wallets still trading
                'consecutive_failures': 0
            }
            
            self.active_sessions[session_id] = session_data
            
            # Start the 4-hour volume generation task
            task = asyncio.create_task(
                self._run_continuous_buy_sell_cycles(session_id)
            )
            self.running_tasks[session_id] = task
            
            logger.info(f"✅ Volume session started - 5 wallets will BUY→SELL {token_contract[:20]}...")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error starting volume session: {e}", exc_info=True)
            return False

    async def _run_continuous_buy_sell_cycles(self, session_id: int):
        """Run continuous BUY → SELL cycles for 4 hours across all 5 wallets"""
        session_data = self.active_sessions.get(session_id)
        if not session_data:
            return
        
        user_id = session_data['user_id']
        token_contract = session_data['token_contract']
        end_time = session_data['end_time']
        
        logger.info(f"🔄 Starting continuous BUY→SELL cycles for session {session_id}")
        logger.info(f"⚡ Strategy: BUY (70%) → IMMEDIATE SELL → Wait 1 min → Repeat")
        
        try:
            while datetime.now() < end_time and session_data['consecutive_failures'] < self.MAX_CONSECUTIVE_FAILURES:
                # Update session data reference
                session_data = self.active_sessions.get(session_id)
                if not session_data:
                    break
                
                cycle_number = session_data['cycles_completed'] + 1
                logger.info(f"🔄 CYCLE {cycle_number} STARTING")
                
                # ================================
                # CHECK WALLET BALANCES
                # ================================
                current_balances = await self._get_current_wallet_balances(session_id)
                active_wallets = []
                
                for wallet_index in range(1, 6):
                    balance = current_balances.get(wallet_index, Decimal('0'))
                    if balance >= self.MIN_TRADE_AMOUNT:
                        active_wallets.append(wallet_index)
                        logger.info(f"   Wallet {wallet_index}: {balance:.6f} SUI available")
                    else:
                        logger.warning(f"   Wallet {wallet_index}: Insufficient balance ({balance:.6f} SUI)")
                
                # Update active wallets
                session_data['active_wallets'] = active_wallets
                session_data['current_balances'] = current_balances
                
                # Stop if no wallets have sufficient balance
                if not active_wallets:
                    logger.info(f"💰 All wallets depleted for session {session_id}")
                    break
                
                logger.info(f"📊 Active wallets: {len(active_wallets)}/5")
                
                # ================================
                # EXECUTE SIMULTANEOUS BUY-SELL CYCLES
                # ================================
                results = await self._execute_all_wallet_buy_sell_cycles(
                    session_id, user_id, token_contract, cycle_number, current_balances, active_wallets
                )
                
                # ================================
                # UPDATE STATISTICS
                # ================================
                successful_swaps = sum(1 for r in results if r.get('success'))
                total_profit = sum(Decimal(str(r.get('profit', 0))) for r in results if r.get('success'))
                total_buy_volume = sum(Decimal(str(r.get('sui_spent', 0))) for r in results if r.get('success'))
                total_sell_volume = sum(Decimal(str(r.get('sui_received', 0))) for r in results if r.get('success'))
                total_volume = total_buy_volume + total_sell_volume
                
                # Update session data
                session_data['cycles_completed'] = cycle_number
                session_data['total_trades'] += successful_swaps * 2  # Buy + Sell
                session_data['total_volume'] += total_volume
                session_data['total_profit'] += total_profit
                session_data['total_buy_volume'] += total_buy_volume
                session_data['total_sell_volume'] += total_sell_volume
                
                # Update consecutive failures
                if successful_swaps > 0:
                    session_data['consecutive_failures'] = 0
                    logger.info(f"✅ CYCLE {cycle_number} COMPLETE: {successful_swaps}/{len(active_wallets)} wallets")
                    logger.info(f"   Buy Volume: {total_buy_volume:.2f} SUI")
                    logger.info(f"   Sell Volume: {total_sell_volume:.2f} SUI")
                    logger.info(f"   Total Volume: {total_volume:.2f} SUI")
                    logger.info(f"   Profit: {total_profit:.6f} SUI")
                else:
                    session_data['consecutive_failures'] += 1
                    logger.warning(f"⚠️ CYCLE {cycle_number} failed: {session_data['consecutive_failures']} consecutive failures")
                
                # Update database
                for result in results:
                    if result.get('success'):
                        self._record_swap_in_db(session_id, user_id, token_contract, result)
                
                # ================================
                # CHECK TIME & CONTINUE
                # ================================
                time_remaining = (end_time - datetime.now()).total_seconds()
                if time_remaining <= 0:
                    logger.info(f"⏰ 4-hour session completed for session {session_id}")
                    break
                
                # Check if we should continue
                if session_data['consecutive_failures'] >= self.MAX_CONSECUTIVE_FAILURES:
                    logger.error(f"❌ Too many consecutive failures, stopping session {session_id}")
                    break
                
                # Wait 1 minute before next cycle
                logger.info(f"⏳ Waiting {self.TRADING_INTERVAL} seconds for next cycle...")
                await asyncio.sleep(self.TRADING_INTERVAL)
            
            # Session completion
            if session_data.get('consecutive_failures', 0) >= self.MAX_CONSECUTIVE_FAILURES:
                error_msg = f"Session stopped: {self.MAX_CONSECUTIVE_FAILURES} consecutive failures"
                logger.error(f"❌ Session {session_id}: {error_msg}")
                await self._complete_session(session_id, error_msg, failed=True)
            else:
                success_msg = f"Volume generation completed"
                logger.info(f"✅ Session {session_id}: {success_msg}")
                await self._complete_session(session_id, success_msg, failed=False)
                
        except Exception as e:
            logger.error(f"❌ Volume generation error for session {session_id}: {e}", exc_info=True)
            await self._complete_session(session_id, f"Error: {str(e)}", failed=True)
        finally:
            # Cleanup
            self.active_sessions.pop(session_id, None)
            self.running_tasks.pop(session_id, None)
            logger.info(f"🧹 Cleaned up session {session_id}")

    async def _get_current_wallet_balances(self, session_id: int) -> Dict[int, Decimal]:
        """Get current balances for all dynamically generated 5 wallets in the session"""
        balances = {}
        session_wallets = self.db.get_session_wallets(session_id)
        
        for wallet in session_wallets:
            wallet_index = wallet['index']
            balance = self.wm.get_wallet_balance(wallet['address'])
            balances[wallet_index] = balance
        return balances

    async def _execute_all_wallet_buy_sell_cycles(
        self, 
        session_id: int, 
        user_id: int, 
        token_contract: str, 
        cycle_number: int,
        current_balances: Dict[int, Decimal],
        active_wallets: List[int]
    ) -> List[Dict]:
        """Execute BUY → SELL cycles on all active wallets simultaneously"""
        tasks = []
        
        logger.info(f"🔄 Executing BUY→SELL on {len(active_wallets)} wallets...")
        
        # Create tasks for all active wallets
        for wallet_index in active_wallets:
            balance = current_balances.get(wallet_index, Decimal('0'))
            
            # Calculate 70% of current balance
            trade_amount = balance * self.TRADE_PERCENTAGE
            
            # Ensure minimum trade amount
            if trade_amount < self.MIN_TRADE_AMOUNT:
                trade_amount = balance  # Use remaining balance
            
            # Ensure we don't exceed balance
            if trade_amount > balance:
                trade_amount = balance
            
            logger.info(f"   Wallet {wallet_index}: Trading {trade_amount:.6f} SUI (70% of {balance:.6f})")
            
            # Fetch explicit private key instead of passing an index
            session_wallets = self.db.get_session_wallets(session_id)
            wallet_data = next((w for w in session_wallets if w['index'] == wallet_index), None)
            private_key = wallet_data['private_key'] if wallet_data else ""
            
            # Create buy-sell cycle task
            task = self._execute_single_wallet_buy_sell_cycle(
                session_id, user_id, token_contract, wallet_index, private_key, trade_amount, cycle_number
            )
            tasks.append(task)
        
        # Execute ALL cycles concurrently (simultaneously)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        processed_results = []
        for i, result in enumerate(results):
            wallet_index = active_wallets[i] if i < len(active_wallets) else i+1
            
            if isinstance(result, Exception):
                logger.error(f"❌ Wallet {wallet_index} cycle error: {result}")
                processed_results.append({
                    'success': False,
                    'wallet_index': wallet_index,
                    'error': str(result),
                    'trade_amount': float(current_balances.get(wallet_index, 0))
                })
            else:
                processed_results.append(result)
                
                if result.get('success'):
                    profit = result.get('profit', 0)
                    profit_percentage = result.get('profit_percentage', 0)
                    logger.info(f"✅ Wallet {wallet_index}: {profit_percentage:+.4f}% ({profit:.6f} SUI)")
                else:
                    logger.warning(f"⚠️ Wallet {wallet_index} failed: {result.get('error', 'Unknown')}")
        
        return processed_results

    async def _execute_single_wallet_buy_sell_cycle(
        self,
        session_id: int,
        user_id: int,
        token_contract: str,
        wallet_index: int,
        private_key: str,
        trade_amount: Decimal,
        cycle_number: int
    ) -> Dict:
        """Execute complete BUY → IMMEDIATE SELL cycle for one wallet"""
        try:
            if trade_amount < self.MIN_TRADE_AMOUNT:
                return {
                    'success': False,
                    'wallet_index': wallet_index,
                    'error': f'Amount too small: {trade_amount:.6f} SUI',
                    'trade_amount': float(trade_amount),
                    'cycle_number': cycle_number
                }
            
            logger.info(f"🔄 W{wallet_index} Cycle {cycle_number}: Executing SUI BUY → SELL using Hop...")
            
            # Execute complete cycle using isolated dynamically generated wallet key
            swap_result = await self.dex.execute_buy_sell_cycle(
                private_key=private_key,
                wallet_index=wallet_index,
                token_contract=token_contract,
                amount_sui=trade_amount
            )
            
            # Add session info to result
            swap_result['session_id'] = session_id
            swap_result['user_id'] = user_id
            swap_result['cycle_number'] = cycle_number
            swap_result['token_contract'] = token_contract
            swap_result['trade_amount'] = float(trade_amount)
            swap_result['trade_percentage'] = 70.0
            swap_result['timestamp'] = datetime.now().isoformat()
            
            return swap_result
            
        except Exception as e:
            logger.error(f"❌ Buy-sell cycle failed for wallet {wallet_index}: {e}")
            return {
                'success': False,
                'wallet_index': wallet_index,
                'error': str(e),
                'trade_amount': float(trade_amount),
                'cycle_number': cycle_number,
                'session_id': session_id,
                'user_id': user_id
            }

    def _record_swap_in_db(self, session_id: int, user_id: int, token_contract: str, swap_result: Dict):
        """Record swap in database with detailed information"""
        try:
            wallet_index = swap_result['wallet_index']
            cycle_number = swap_result.get('cycle_number', 0)
            trade_amount = swap_result.get('trade_amount', 0)
            profit = swap_result.get('profit', 0)
            
            # Record buy trade - BUYING TOKEN with SUI
            self.db.record_trade(
                user_id=user_id,
                token_contract=token_contract,
                sub_wallet_index=wallet_index,
                action='buy',
                amount=swap_result.get('sui_spent', trade_amount),
                price=1.0,
                session_id=session_id,
                tx_hash=swap_result.get('buy_tx_hash'),
                profit_loss=profit,
                cycle_number=cycle_number,
                trade_percentage=70.0,
                token_amount=swap_result.get('tokens_bought', 0)  # Add token amount for buy
            )
            
            # Record sell trade - SELLING TOKEN for SUI (BACK TO NATIVE TOKEN)
            # IMPORTANT: For sell action, the 'amount' should be SUI received (not token amount)
            # This is the key fix - we're selling tokens back to get SUI
            self.db.record_trade(
                user_id=user_id,
                token_contract=token_contract,
                sub_wallet_index=wallet_index,
                action='sell',
                amount=swap_result.get('sui_received', 0),  # SUI received from selling tokens
                price=1.0,
                session_id=session_id,
                tx_hash=swap_result.get('sell_tx_hash'),
                profit_loss=profit,
                cycle_number=cycle_number,
                trade_percentage=70.0,
                token_amount=swap_result.get('tokens_sold', 0)  # Token amount sold
            )
            
            # Update session volume
            buy_volume = swap_result.get('sui_spent', trade_amount)
            sell_volume = swap_result.get('sui_received', 0)  # SUI received from sell
            total_volume = buy_volume + sell_volume
            
            self.db.update_session_volume(session_id, total_volume)
            self.db.update_session_profit(session_id, profit)
            
            logger.debug(f"📝 Recorded swap for wallet {wallet_index}, cycle {cycle_number}")
            logger.debug(f"   Buy: {buy_volume:.6f} SUI spent for tokens")
            logger.debug(f"   Sell: {sell_volume:.6f} SUI received for tokens")
            
        except Exception as e:
            logger.error(f"❌ Error recording swap in DB: {e}")

    async def _complete_session(self, session_id: int, message: str, failed: bool = False):
        """Complete a volume generation session with detailed statistics"""
        try:
            # Mark session as completed in database
            self.db.mark_session_completed(session_id)
            
            # Get final statistics from session data
            session_data = self.active_sessions.get(session_id, {})
            cycles = session_data.get('cycles_completed', 0)
            trades = session_data.get('total_trades', 0)
            total_volume = session_data.get('total_volume', Decimal('0'))
            total_profit = session_data.get('total_profit', Decimal('0'))
            buy_volume = session_data.get('total_buy_volume', Decimal('0'))
            sell_volume = session_data.get('total_sell_volume', Decimal('0'))
            deposit = session_data.get('deposit_amount', Decimal('0'))
            fee = session_data.get('fee_amount', Decimal('500'))
            trading_amount = deposit - fee
            
            # Get final wallet balances (should be in SUI since tokens were sold back)
            final_balances = await self._get_current_wallet_balances(session_id)
            total_remaining = sum(final_balances.values())
            
            completion_message = f"""
{'❌' if failed else '✅'} **VOLUME SESSION #{session_id} COMPLETED**

📊 **Deposit Statistics:**
• Total Deposit: {float(deposit):,.2f} SUI
• Fee Collected: {float(fee)} SUI
• Trading Amount: {float(trading_amount):,.2f} SUI
• Remainder in Main: {float(session_data.get('remainder', 0)):,} SUI

📈 **Trading Performance:**
• Cycles Completed: {cycles}
• Total Trades: {trades} (Buy + Sell)
• Buy Volume: {float(buy_volume):,.2f} SUI (SUI → Token)
• Sell Volume: {float(sell_volume):,.2f} SUI (Token → SUI)
• Total Volume: {float(total_volume):,.2f} SUI
• Total Profit: {float(total_profit):+.6f} SUI
• Remaining in Wallets: {float(total_remaining):,.6f} SUI

🎯 **Trading Strategy:**
• Wallets: 5 active
• Trade Size: 70% of current balance
• Cycle: BUY (SUI → Token) → IMMEDIATE SELL (Token → SUI) → Wait 1 minute
• Duration: 4 hours target

📝 **Status:** {message}

💰 **Funds remain in sub-wallets for withdrawal (in SUI)**
🚀 **Ready for another token?** Use /deposit
            """
            
            # Store completion message
            self.db.store_completion_message(session_id, completion_message)
            
            # Log final statistics
            logger.info("=" * 70)
            logger.info(f"📊 SESSION #{session_id} FINAL STATISTICS")
            logger.info(f"• Cycles: {cycles}")
            logger.info(f"• Trades: {trades}")
            logger.info(f"• Buy Volume (SUI spent): {float(buy_volume):,.2f} SUI")
            logger.info(f"• Sell Volume (SUI received): {float(sell_volume):,.2f} SUI")
            logger.info(f"• Total Volume: {float(total_volume):,.2f} SUI")
            logger.info(f"• Total Profit: {float(total_profit):+.6f} SUI")
            logger.info(f"• Remaining in Wallets: {float(total_remaining):,.6f} SUI")
            logger.info(f"• Status: {'FAILED' if failed else 'COMPLETED'}")
            logger.info("=" * 70)
            
            logger.info(f"📤 Session {session_id} completed: {message}")
            
        except Exception as e:
            logger.error(f"❌ Error completing session {session_id}: {e}")

    def get_session_progress(self, session_id: int) -> Dict:
        """Get detailed progress of a volume generation session"""
        if session_id not in self.active_sessions:
            return {'active': False}
        
        session_data = self.active_sessions[session_id]
        now = datetime.now()
        
        # Calculate progress
        total_duration = self.SESSION_DURATION
        elapsed = (now - session_data['start_time']).total_seconds()
        progress_percent = min(100, (elapsed / total_duration) * 100)
        
        # Time remaining
        time_remaining = max(0, (session_data['end_time'] - now).total_seconds())
        hours_remaining = int(time_remaining // 3600)
        minutes_remaining = int((time_remaining % 3600) // 60)
        seconds_remaining = int(time_remaining % 60)
        
        # Get current balances (should be in SUI)
        current_balances = session_data.get('current_balances', {})
        total_current_balance = sum(current_balances.values())
        
        return {
            'active': True,
            'session_id': session_id,
            'user_id': session_data['user_id'],
            'token_contract': session_data['token_contract'],
            'progress_percent': round(progress_percent, 1),
            'time_remaining': f"{hours_remaining:02d}:{minutes_remaining:02d}:{seconds_remaining:02d}",
            'time_remaining_seconds': int(time_remaining),
            'cycles_completed': session_data['cycles_completed'],
            'total_trades': session_data['total_trades'],
            'total_volume': float(session_data.get('total_volume', 0)),
            'total_profit': float(session_data.get('total_profit', 0)),
            'buy_volume': float(session_data.get('total_buy_volume', 0)),
            'sell_volume': float(session_data.get('total_sell_volume', 0)),
            'deposit_amount': float(session_data.get('deposit_amount', 0)),
            'fee_amount': float(session_data.get('fee_amount', 500)),
            'trading_amount': float(session_data.get('deposit_amount', 0) - session_data.get('fee_amount', 500)),
            'wallets_active': len(session_data.get('active_wallets', [])),
            'total_wallets': 5,
            'current_balances': {k: float(v) for k, v in current_balances.items()},
            'total_current_balance': float(total_current_balance),
            'consecutive_failures': session_data.get('consecutive_failures', 0),
            'trade_percentage': 70.0,
            'start_time': session_data['start_time'].strftime('%H:%M:%S'),
            'end_time': session_data['end_time'].strftime('%H:%M:%S'),
            'estimated_completion': session_data['end_time'].strftime('%H:%M:%S'),
            'is_running': True,
            'trading_strategy': 'BUY (SUI → Token) → SELL (Token → SUI)'
        }

    def get_active_sessions_info(self) -> Dict[int, Dict]:
        """Get information about all active volume generation sessions"""
        active_info = {}
        
        for session_id, session_data in self.active_sessions.items():
            progress = self.get_session_progress(session_id)
            if progress['active']:
                active_info[session_id] = progress
        
        return active_info

    def stop_volume_session(self, session_id: int) -> bool:
        """Stop a specific volume generation session"""
        if session_id in self.running_tasks:
            try:
                self.running_tasks[session_id].cancel()
                logger.info(f"🛑 Stopping volume session {session_id}")
                
                # Clean up
                if session_id in self.active_sessions:
                    self.active_sessions.pop(session_id)
                self.running_tasks.pop(session_id)
                
                # Mark as stopped in database
                self.db.mark_session_stopped(session_id, "Manually stopped by user")
                
                return True
            except Exception as e:
                logger.error(f"❌ Error stopping session {session_id}: {e}")
                return False
        return False

    async def stop_all_sessions(self):
        """Stop all active volume generation sessions"""
        logger.info("🛑 Stopping all volume sessions...")
        
        sessions_to_stop = list(self.running_tasks.keys())
        for session_id in sessions_to_stop:
            self.stop_volume_session(session_id)
        
        # Wait for cleanup
        await asyncio.sleep(1)
        logger.info(f"✅ Stopped {len(sessions_to_stop)} volume sessions")

    def get_session_summary(self, session_id: int) -> Dict:
        """Get comprehensive session summary"""
        if session_id not in self.active_sessions:
            # Try to get from database
            session_stats = self.db.get_session_stats(session_id)
            if session_stats:
                return {
                    'active': False,
                    'from_database': True,
                    **session_stats
                }
            return {'active': False, 'error': 'Session not found'}
        
        # Get live session data
        progress = self.get_session_progress(session_id)
        session_data = self.active_sessions[session_id]
        
        summary = {
            **progress,
            'detailed_stats': {
                'initial_per_wallet': float(session_data.get('initial_per_wallet', 0)),
                'initial_balances': {k: float(v) for k, v in session_data.get('initial_balances', {}).items()},
                'cycles': session_data.get('cycles_completed', 0),
                'consecutive_failures': session_data.get('consecutive_failures', 0),
                'active_wallets': session_data.get('active_wallets', []),
                'strategy': 'BUY (SUI → Token) → IMMEDIATE SELL (Token → SUI)',
                'trade_percentage': '70%',
                'interval_seconds': self.TRADING_INTERVAL
            }
        }
        
        return summary