# trading_engine.py - Complete Trading Engine
import asyncio
import logging
import time
from datetime import datetime, timedelta
from database import SuiDatabase
from wallet_manager import WalletManager

logger = logging.getLogger(__name__)

class TradingEngine:
    def __init__(self, database: SuiDatabase, wallet_manager: WalletManager):
        self.db = database
        self.wm = wallet_manager
        self.MIN_TRADE_AMOUNT = 0.1  # Minimum SUI per trade
        self.TRADING_INTERVAL = 60   # 1 minute between cycles
        self.active_sessions = {}    # Track running sessions
        self.is_running = False
        
        logger.info("✅ Trading Engine initialized")

    async def start_trading_for_session(self, session_id):
        """Start continuous trading for a session"""
        try:
            session = self.db.get_session_for_trading(session_id)
            if not session:
                logger.error(f"❌ Session {session_id} not found or not active")
                return

            session_id, user_id, token_contract, original_amount, trading_amount, current_balance, status, total_trades, total_volume, completed_at, created_at = session
            
            logger.info(f"🚀 Starting trading for session {session_id}, user {user_id}, token {token_contract[:20]}...")
            
            # Add to active sessions
            self.active_sessions[session_id] = {
                'user_id': user_id,
                'token_contract': token_contract,
                'trading_amount': trading_amount,
                'start_time': datetime.now(),
                'cycles_completed': 0
            }
            
            cycle_count = 0
            consecutive_failures = 0
            max_consecutive_failures = 3
            
            while await self.is_session_active(session_id) and consecutive_failures < max_consecutive_failures:
                cycle_count += 1
                logger.info(f"🔄 Trading cycle {cycle_count} for session {session_id}")
                
                # Execute trading cycle
                successful_trades = await self.execute_trading_cycle(session_id, cycle_count)
                
                if successful_trades > 0:
                    consecutive_failures = 0  # Reset failure counter
                    logger.info(f"✅ Cycle {cycle_count}: {successful_trades}/5 wallets successful")
                else:
                    consecutive_failures += 1
                    logger.warning(f"⚠️ Cycle {cycle_count} failed: {consecutive_failures} consecutive failures")
                
                # Update session stats
                self.active_sessions[session_id]['cycles_completed'] = cycle_count
                
                # Check if session should complete
                if not await self.is_session_active(session_id):
                    break
                
                # Wait for next cycle
                logger.info(f"⏰ Waiting {self.TRADING_INTERVAL} seconds for next cycle...")
                await asyncio.sleep(self.TRADING_INTERVAL)
            
            if consecutive_failures >= max_consecutive_failures:
                logger.error(f"❌ Session {session_id} stopped due to {max_consecutive_failures} consecutive failures")
                await self.notify_session_stopped(session_id, user_id, "Too many consecutive trade failures")
            else:
                logger.info(f"✅ Trading completed for session {session_id} after {cycle_count} cycles")
                await self.notify_session_completion(session_id, user_id)
                
        except Exception as e:
            logger.error(f"❌ Trading error for session {session_id}: {e}")
            await self.notify_session_stopped(session_id, user_id, str(e))
        finally:
            # Remove from active sessions
            self.active_sessions.pop(session_id, None)

    async def execute_trading_cycle(self, session_id, cycle_number):
        """Execute one trading cycle across all 5 wallets simultaneously"""
        session_data = self.active_sessions.get(session_id)
        if not session_data:
            return 0

        user_id = session_data['user_id']
        token_contract = session_data['token_contract']
        
        # Get current session balance
        current_balance = self.get_session_balance(session_id)
        if current_balance < self.MIN_TRADE_AMOUNT:
            logger.info(f"💰 Session {session_id} balance depleted: {current_balance} SUI")
            self.db.mark_session_completed(session_id)
            return 0
        
        # Calculate trade amount per wallet (2% of remaining balance divided by 5)
        trade_amount_per_wallet = (current_balance * 0.02) / 5
        
        # Ensure minimum trade amount
        if trade_amount_per_wallet < self.MIN_TRADE_AMOUNT:
            trade_amount_per_wallet = self.MIN_TRADE_AMOUNT
        
        # Ensure we don't exceed remaining balance
        total_trade_amount = trade_amount_per_wallet * 5
        if total_trade_amount > current_balance:
            trade_amount_per_wallet = current_balance / 5
        
        logger.info(f"💸 Cycle {cycle_number}: Trading {trade_amount_per_wallet:.4f} SUI per wallet")
        
        # Execute trades across all wallets
        tasks = []
        for wallet_index in range(1, 6):
            task = self.execute_wallet_trade(
                session_id, user_id, token_contract, wallet_index, trade_amount_per_wallet, cycle_number
            )
            tasks.append(task)
        
        # Execute all wallet trades concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successful trades
        successful_trades = 0
        for i, result in enumerate(results, 1):
            if isinstance(result, Exception):
                logger.error(f"❌ Wallet {i} trade failed: {result}")
            elif result and result.get('success'):
                successful_trades += 1
                logger.info(f"✅ Wallet {i} trade successful: {result.get('amount', 0):.4f} SUI")
            else:
                logger.warning(f"⚠️ Wallet {i} trade failed: {result.get('error', 'Unknown error')}")
        
        return successful_trades

    async def execute_wallet_trade(self, session_id, user_id, token_contract, wallet_index, trade_amount, cycle_number):
        """Execute buy-sell cycle for a single wallet"""
        try:
            # Check if we still have enough balance
            current_balance = self.get_session_balance(session_id)
            if current_balance < trade_amount:
                return {'success': False, 'reason': 'insufficient_balance'}
            
            logger.info(f"🔄 Wallet {wallet_index} executing trade: {trade_amount:.4f} SUI")
            
            # Step 1: Execute buy order
            buy_result = self.wm.execute_immediate_swap(wallet_index, token_contract, trade_amount)
            
            if not buy_result.get('buy_success', False):
                return {'success': False, 'error': f'Buy failed: {buy_result.get("error")}'}
            
            # Record buy trade
            buy_price = 1.0  # Simulated price - would get from DEX in real implementation
            self.db.record_trade(
                user_id, token_contract, wallet_index, 
                'buy', trade_amount, buy_price, session_id,
                buy_result.get('buy_tx_hash')
            )
            
            # Step 2: Execute immediate sell order
            sell_result = self.wm.execute_immediate_swap(wallet_index, token_contract, trade_amount)
            
            if not sell_result.get('sell_success', False):
                # If sell fails, we still record the buy and mark as problematic
                logger.error(f"❌ Wallet {wallet_index} sell failed after successful buy")
                return {'success': False, 'error': f'Sell failed: {sell_result.get("error")}'}
            
            # Record sell trade with simulated profit
            sell_price = buy_price * 1.001  # 0.1% profit simulation
            self.db.record_trade(
                user_id, token_contract, wallet_index,
                'sell', trade_amount, sell_price, session_id,
                sell_result.get('sell_tx_hash')
            )
            
            # Calculate and log profit
            profit = (sell_price - buy_price) * trade_amount
            logger.info(f"💰 Wallet {wallet_index} profit: {profit:.6f} SUI")
            
            return {
                'success': True, 
                'amount': trade_amount,
                'wallet': wallet_index,
                'profit': profit,
                'buy_tx': buy_result.get('buy_tx_hash'),
                'sell_tx': sell_result.get('sell_tx_hash')
            }
            
        except Exception as e:
            logger.error(f"❌ Wallet {wallet_index} trade execution failed: {e}")
            return {'success': False, 'error': str(e)}

    async def is_session_active(self, session_id):
        """Check if session is still active and has balance"""
        try:
            # Check database status
            session = self.db.get_session_for_trading(session_id)
            if not session:
                return False
            
            # Check balance
            current_balance = session[5]  # current_balance field
            if current_balance < self.MIN_TRADE_AMOUNT:
                self.db.mark_session_completed(session_id)
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error checking session {session_id} status: {e}")
            return False

    def get_session_balance(self, session_id):
        """Get current balance for a session"""
        try:
            session = self.db.get_session_for_trading(session_id)
            return session[5] if session else 0  # current_balance field
        except Exception as e:
            logger.error(f"❌ Error getting balance for session {session_id}: {e}")
            return 0

    async def notify_session_completion(self, session_id, user_id):
        """Notify user that their trading session has completed"""
        try:
            session_stats = self.db.get_session_stats(session_id)
            if not session_stats:
                return
            
            session = session_stats['session']
            allocations = session_stats.get('allocations', [])
            trade_count = session_stats.get('trade_count', 0)
            
            session_id, user_id, token_contract, original_amount, trading_amount, current_balance, status, total_trades, total_volume, completed_at, created_at = session
            
            # Calculate session duration
            duration = self.calculate_duration(created_at, completed_at or datetime.now())
            
            # Calculate performance
            remaining_balance = current_balance
            total_traded = trading_amount - remaining_balance
            profit_loss = remaining_balance - trading_amount  # Simple P&L calculation
            
            completion_message = f"""
🎉 **TRADING SESSION COMPLETED!**

📊 **Final Statistics:**
• Token: `{token_contract[:20]}...`
• Initial Capital: {trading_amount:,.1f} SUI
• Final Balance: {remaining_balance:,.1f} SUI
• Total Trades: {trade_count:,}
• Total Volume: {total_traded:,.1f} SUI

💰 **Result:** {profit_loss:+,.1f} SUI

⏱️ **Session Duration:** {duration}

🔄 **Trading Summary:**
• Buy → Immediate Sell strategy
• 5 wallets trading simultaneously
• 1-minute intervals between cycles

🚀 **Ready to trade another token?** Use /deposit to start a new session!
            """
            
            # In a real implementation, you would send this via Telegram
            logger.info(f"📤 Completion notification for user {user_id}: {completion_message}")
            
            # Store completion message for when user checks status
            self.db.store_completion_message(session_id, completion_message)
            
        except Exception as e:
            logger.error(f"❌ Error sending completion notification: {e}")

    async def notify_session_stopped(self, session_id, user_id, reason):
        """Notify user that their trading session was stopped due to errors"""
        try:
            error_message = f"""
❌ **TRADING SESSION STOPPED**

⚠️ **Reason:** {reason}

🔧 **What happened:**
Your trading session encountered multiple errors and was automatically stopped to protect your funds.

📊 **Current status has been saved.**
💰 **Remaining funds are safe.**

🔄 **You can start a new trading session anytime using /deposit**

Need help? Contact support.
            """
            
            # In a real implementation, you would send this via Telegram
            logger.info(f"📤 Error notification for user {user_id}: {error_message}")
            
            # Store error message
            self.db.store_completion_message(session_id, error_message)
            
        except Exception as e:
            logger.error(f"❌ Error sending stop notification: {e}")

    def calculate_duration(self, start_time, end_time):
        """Calculate duration between start and end times"""
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        if isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        
        duration = end_time - start_time
        hours = duration.seconds // 3600
        minutes = (duration.seconds % 3600) // 60
        seconds = duration.seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        else:
            return f"{minutes}m {seconds}s"

    def get_active_sessions_info(self):
        """Get information about all active trading sessions"""
        active_info = {}
        for session_id, session_data in self.active_sessions.items():
            current_balance = self.get_session_balance(session_id)
            progress = ((session_data['trading_amount'] - current_balance) / session_data['trading_amount']) * 100
            
            active_info[session_id] = {
                'user_id': session_data['user_id'],
                'token_contract': session_data['token_contract'],
                'trading_amount': session_data['trading_amount'],
                'current_balance': current_balance,
                'progress': progress,
                'cycles_completed': session_data['cycles_completed'],
                'start_time': session_data['start_time']
            }
        
        return active_info

    def stop_trading_for_session(self, session_id):
        """Stop trading for a specific session"""
        if session_id in self.active_sessions:
            # The session will naturally stop in the next cycle check
            logger.info(f"🛑 Stopping trading for session {session_id}")
            return True
        return False

    async def stop_all_trading(self):
        """Stop all active trading sessions"""
        logger.info("🛑 Stopping all trading sessions...")
        sessions_to_stop = list(self.active_sessions.keys())
        
        for session_id in sessions_to_stop:
            self.stop_trading_for_session(session_id)
        
        # Wait a moment for sessions to stop
        await asyncio.sleep(2)
        
        logger.info(f"✅ Stopped {len(sessions_to_stop)} trading sessions")

# Enhanced Database Methods needed for Trading Engine
def add_database_methods():
    """Add these methods to your existing SuiDatabase class"""
    
    def get_session_for_trading(self, session_id):
        """Get session details for trading"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM trading_sessions 
            WHERE session_id = ? AND status = 'active'
        ''', (session_id,))
        
        session = cursor.fetchone()
        conn.close()
        return session

    def mark_session_completed(self, session_id):
        """Mark a session as completed"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE trading_sessions 
            SET status = 'completed', completed_at = CURRENT_TIMESTAMP
            WHERE session_id = ?
        ''', (session_id,))
        
        conn.commit()
        conn.close()
        logger.info(f"✅ Session {session_id} marked as completed")

    def get_session_stats(self, session_id):
        """Get statistics for a trading session"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM trading_sessions WHERE session_id = ?
        ''', (session_id,))
        
        session = cursor.fetchone()
        
        if session:
            # Get trade count
            cursor.execute('''
                SELECT COUNT(*) FROM trades WHERE session_id = ?
            ''', (session_id,))
            
            trade_count = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'session': session,
                'trade_count': trade_count
            }
        
        conn.close()
        return None

    def store_completion_message(self, session_id, message):
        """Store completion/error message for a session"""
        conn = self.connect()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS session_messages (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                message_type TEXT,
                message_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES trading_sessions (session_id)
            )
        ''')
        
        cursor.execute('''
            INSERT INTO session_messages (session_id, message_type, message_text)
            VALUES (?, 'completion', ?)
        ''', (session_id, message))
        
        conn.commit()
        conn.close()

    def connect(self):
        """Database connection helper"""
        return sqlite3.connect(self.db_path)

    # Add these methods to SuiDatabase class
    SuiDatabase.get_session_for_trading = get_session_for_trading
    SuiDatabase.mark_session_completed = mark_session_completed
    SuiDatabase.get_session_stats = get_session_stats
    SuiDatabase.store_completion_message = store_completion_message
    SuiDatabase.connect = connect

# Initialize the enhanced database methods
add_database_methods()