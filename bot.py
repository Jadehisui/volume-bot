# bot.py - Fixed with proper initialization
import asyncio
import os
import logging
from decimal import Decimal
from typing import Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler
)
from dotenv import load_dotenv

from database import SuiDatabase
from wallet_manager import WalletManager
from volume_engine import VolumeEngine

load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('sui_volume_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SuiVolumeBot:
    def __init__(self):
        # Load Telegram token
        self.token = os.getenv("TELEGRAM_API_KEY")
        if not self.token:
            raise ValueError("❌ TELEGRAM_API_KEY is required in .env")
        
        # Bot configuration
        self.min_deposit = Decimal('20')
        self.fee_amount = Decimal('2')
        
        # Initialize components
        self.db = SuiDatabase()
        self.wallet_manager = WalletManager(database=self.db)
        self.volume_engine = VolumeEngine(self.db, self.wallet_manager)
        
        # Get wallet addresses for display
        self.main_wallet_address = self.wallet_manager.main_wallet['address']
        self.fee_wallet_address = self.wallet_manager.fee_wallet
        
        # User states
        self.user_states = {}  # {user_id: {'state': 'awaiting_token', 'data': {}}}
        
        logger.info("✅ Sui Volume Bot initialized")
        logger.info(f"💰 Main wallet: {self.main_wallet_address}")
        logger.info(f"💸 Fee wallet: {self.fee_wallet_address}")
        
        # SIMPLIFIED: Skip validation for now
        try:
            self.db.init_database()
            logger.info("✅ Database initialized")
            
            # Check RPC connection (Wallet Manager does validation)
            logger.info("📦 Initialization complete")
            
        except Exception as e:
            logger.warning(f"⚠️ Setup warning: {e}")
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        try:
            user = update.effective_user
            self.db.add_user(user.id, user.username or "Unknown")
            
            welcome_msg = f"""
🤖 **Welcome to Sui Volume Bot!** 🚀

Generate massive trading volume for your token using our 5-wallet system!

**How it works:**
1️⃣ Send **{self.min_deposit:,}+ SUI** to main wallet
2️⃣ We collect a small operational fee
3️⃣ Remaining divided equally among 5 wallets
4️⃣ 5 wallets trade your token for 4 hours:
   • **70% of balance per trade**
   


**Main Wallet:** `{self.main_wallet_address}`
**Minimum:** {self.min_deposit:,} SUI


Use /deposit to get started!
            """
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 Start Volume", callback_data="start_deposit")],
                [InlineKeyboardButton("📊 Check Status", callback_data="check_status")],
                [InlineKeyboardButton("❓ Help", callback_data="show_help")]
            ])
            
            await update.message.reply_text(welcome_msg, parse_mode='Markdown', reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"❌ /start error: {e}")
            await update.message.reply_text("❌ Failed to start bot. Please try again.")
    
    async def deposit_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /deposit command"""
        try:
            user_id = update.effective_user.id
            
            # Clear any existing state
            self.user_states.pop(user_id, None)
            
            # Check main wallet balance
            main_balance = self.wallet_manager.get_wallet_balance(self.main_wallet_address)
            
            deposit_msg = f"""
💰 **VOLUME GENERATION DEPOSIT**

**Step 1:** Send **{self.min_deposit:,}+ SUI** to:
`{self.main_wallet_address}`

**Step 2:** After sending, reply with your token contract address

**Requirements:**
• Minimum: {self.min_deposit:,} SUI
• Fee: A standard operational fee is deducted
• Trading: Remaining divided equally among 5 wallets
• Strategy: 70% of balance per trade

**Current Main Wallet Balance:** {float(main_balance):,.2f} SUI
{'✅ **Ready for deposits!**' if main_balance >= self.min_deposit else '❌ **Waiting for deposits...**'}

**Reply with your token contract address (0x...) after sending SUI**
            """
            
            # Set user state
            self.user_states[user_id] = {
                'state': 'awaiting_token',
                'data': {}
            }
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Check Balance", callback_data="check_balance")],
                [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_deposit")]
            ])
            
            await update.message.reply_text(deposit_msg, parse_mode='Markdown', reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"❌ /deposit error: {e}")
            await update.message.reply_text("❌ Failed to process deposit command.")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle user messages"""
        try:
            user_id = update.effective_user.id
            message_text = update.message.text.strip()
            
            user_state = self.user_states.get(user_id, {})
            
            if user_state.get('state') == 'awaiting_token':
                # Validate token contract address
                if not self._is_valid_contract_address(message_text):
                    await update.message.reply_text(
                        "❌ Invalid contract address format. Please provide a valid 0x... address (42 characters)."
                    )
                    return
                
                # Check main wallet balance
                main_balance = self.wallet_manager.get_wallet_balance(self.main_wallet_address)
                
                if main_balance < self.min_deposit:
                    await update.message.reply_text(
                        f"""
❌ **Insufficient Balance**

Main wallet has {float(main_balance):,.2f} SUI
Required: {float(self.min_deposit):,} SUI

Please send {float(self.min_deposit):,}+ SUI to:
`{self.main_wallet_address}`

Then provide your token address again.
                        """,
                        parse_mode='Markdown'
                    )
                    return
                
                # Process deposit
                await self._process_user_deposit(user_id, message_text, context)
                
                # Clear user state
                self.user_states.pop(user_id, None)
                
            else:
                await update.message.reply_text(
                    "Please use /deposit to start the volume generation process first."
                )
                
        except Exception as e:
            logger.error(f"❌ Message handling error: {e}")
            await update.message.reply_text("❌ Failed to process your message.")
    
    async def _process_user_deposit(self, user_id: int, token_contract: str, context: ContextTypes.DEFAULT_TYPE):
        """Process user deposit and start volume generation"""
        try:
            # Send processing message
            processing_msg = await context.bot.send_message(
                chat_id=user_id,
                text="🔄 Processing your deposit... This may take a minute.",
                parse_mode='Markdown'
            )
            
            # Wait for deposit to hit RPC
            deposit_detected, current_balance = await self.wallet_manager.wait_for_deposit(
                self.main_wallet_address, self.min_deposit
            )
            
            if not deposit_detected:
                await processing_msg.edit_text(
                    f"❌ **Deposit not detected yet.**\n\nPlease ensure you sent {float(self.min_deposit):,} SUI to:\n`{self.main_wallet_address}`\n\nBalance: {float(current_balance):,.2f} SUI",
                    parse_mode='Markdown'
                )
                return

            # Create trading session in database FIRST to get the ID
            trading_amount = current_balance - self.wallet_manager.FEE_AMOUNT
            session_id = self.db.create_trading_session(
                user_id, token_contract, float(current_balance), float(trading_amount)
            )
            
            # Process deposit (fees + distribute to 5 SESSION SPECIFIC wallets)
            deposit_result = self.wallet_manager.process_deposit(current_balance, session_id)
            
            if not deposit_result['success']:
                await processing_msg.edit_text(
                    f"❌ Deposit processing failed:\n{deposit_result.get('error', 'Unknown error')}",
                    parse_mode='Markdown'
                )
                return
            
            # Start 4-hour volume generation
            success = await self.volume_engine.start_volume_session(
                session_id, token_contract, current_balance
            )
            
            if not success:
                await processing_msg.edit_text(
                    "❌ Failed to start volume generation. Please contact support.",
                    parse_mode='Markdown'
                )
                return
            
            # Send success message
            successful_wallets = deposit_result['wallets_funded']
            amount_per_wallet = deposit_result['amount_per_wallet']
            
            success_msg = f"""
🎉 **VOLUME GENERATION INITIATED!** 🚀

✅ **Deposit Detected:** {float(current_balance):,.2f} SUI
✅ **Trading Amount:** {float(trading_amount):,.2f} SUI
✅ **Wallets Funded:** {successful_wallets}/5
✅ **Token:** `{token_contract[:20]}...`

📊 **Distribution:**
• Each of 5 wallets: {amount_per_wallet:,} SUI

⚡ **Volume Strategy Active:**
• {successful_wallets} wallets trading simultaneously
• **70% of balance** per trade
• Buy → Immediate Sell → Wait 1 minute
• Continuous for 4 hours
• Token: {token_contract[:20]}...

⏰ **Duration:** 4 hours
🔄 **Next cycle:** Starting now!

Use /status to monitor progress!
            """
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 View Status", callback_data=f"status_{session_id}")],
                [InlineKeyboardButton("💰 New Volume", callback_data="new_deposit")]
            ])
            
            await processing_msg.edit_text(success_msg, parse_mode='Markdown', reply_markup=keyboard)
            
            logger.info(f"✅ Volume generation started for user {user_id}, session {session_id}")
            
        except Exception as e:
            logger.error(f"❌ Deposit processing error: {e}", exc_info=True)
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"❌ Error processing deposit: {str(e)[:200]}",
                    parse_mode='Markdown'
                )
            except:
                pass
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        try:
            user_id = update.effective_user.id
            
            # Get user's active sessions from database
            # For now, just show a simple message
            status_msg = """
📊 **VOLUME BOT STATUS**

The bot is running and ready to process deposits!

**How to start:**
1. Use /deposit to get main wallet address
2. Send {self.min_deposit:,}+ SUI to the address
3. Provide your token contract address
4. We'll start 4-hour volume generation

**Current Status:** ✅ **Operational**
**Trading Strategy:** 70% per trade, 1-minute intervals
**Duration:** 4 hours per session
**Wallets:** 5 sub-wallets trading simultaneously
            """
            
            await update.message.reply_text(status_msg, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"❌ /status error: {e}")
            await update.message.reply_text("❌ Failed to get status.")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_msg = f"""
🆘 **SUI VOLUME BOT HELP** 🆘

**Commands:**
/start - Start the bot
/deposit - Start volume generation
/status - Check bot status  
/help - This message

**How It Works:**
1. Use /deposit to get main wallet address
2. Send {self.min_deposit:,}+ SUI 
3. Provide your token contract address
4. We collect a standard operational fee
5. Remaining divided equally among 5 wallets
6. 5 wallets continuously trade your token

**Volume Strategy:**
• 5 wallets trading simultaneously
• **70% of current balance** per trade
• Buy → Immediate Sell → Wait 1 minute
• 4-hour continuous trading
• Maximum volume generation

**Fee Structure:**
• Minimum deposit: {self.min_deposit:,} SUI
• Fixed fee: Included

**Support:**
Main Wallet: `{self.main_wallet_address}`
Fee Wallet: `{self.fee_wallet_address}`
        """
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 Start Volume", callback_data="start_deposit")],
            [InlineKeyboardButton("📊 Check Status", callback_data="check_status")]
        ])
        
        await update.message.reply_text(help_msg, parse_mode='Markdown', reply_markup=keyboard)
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        try:
            query = update.callback_query
            await query.answer()
            
            data = query.data
            
            if data == "start_deposit":
                # Create a mock update for the command
                mock_update = Update(
                    update_id=update.update_id,
                    message=query.message,
                    callback_query=query
                )
                await self.deposit_command(mock_update, context)
            elif data == "check_status":
                mock_update = Update(
                    update_id=update.update_id,
                    message=query.message,
                    callback_query=query
                )
                await self.status_command(mock_update, context)
            elif data == "check_balance":
                await self._send_balance_check(query)
            elif data.startswith("status_"):
                session_id = int(data.split("_")[1])
                await self._send_session_status(query, session_id)
            elif data == "refresh_deposit":
                await self._refresh_deposit(query)
            elif data == "new_deposit":
                mock_update = Update(
                    update_id=update.update_id,
                    message=query.message,
                    callback_query=query
                )
                await self.deposit_command(mock_update, context)
            elif data == "show_help":
                mock_update = Update(
                    update_id=update.update_id,
                    message=query.message,
                    callback_query=query
                )
                await self.help_command(mock_update, context)
                
        except Exception as e:
            logger.error(f"❌ Callback error: {e}")
            try:
                await query.edit_message_text("❌ Error processing your request.")
            except:
                pass
    
    async def _send_balance_check(self, query):
        """Send main wallet balance check"""
        try:
            balance = self.wallet_manager.get_wallet_balance(self.main_wallet_address)
            
            msg = f"""
💰 **MAIN WALLET BALANCE**

**Address:** `{self.main_wallet_address}`
**Required:** {float(self.min_deposit):,} SUI

{'✅ **Ready for volume generation!**' if balance >= self.min_deposit else '❌ **Waiting for deposit...**'}
            """
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data="check_balance")],
                [InlineKeyboardButton("💰 Start Volume", callback_data="start_deposit")]
            ])
            
            await query.edit_message_text(msg, parse_mode='Markdown', reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"❌ Balance check error: {e}")
            await query.edit_message_text("❌ Error checking balance.")
    
    async def _send_session_status(self, query, session_id: int):
        """Send session status"""
        try:
            # First fetch the session status
            session = self.db.get_session_for_trading(session_id)
            statusText = "will be available here once the session starts."
            mnemonicText = ""
            
            if session:
                statusText = f"Status: {session[6]}"
                
            # If we have generated session wallets, show them
            session_wallets = self.db.get_session_wallets(session_id)
            if session_wallets and len(session_wallets) > 0:
                mnemonicText = "\n\n🔐 **Your Wallet Keys (DO NOT SHARE):**\n"
                for w in session_wallets:
                    mnemonicText += f"Wallet {w['index']} Pk:\n`{w['private_key']}`\n\n"
                    
            msg = f"""
📊 **SESSION #{session_id}**
{statusText}

For now, the bot is ready to process deposits!

**Next Steps:**
1. Send {self.min_deposit:,}+ SUI to main wallet
2. Provide token contract address
3. We'll start 70% volume generation
{mnemonicText}
            """
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data=f"status_{session_id}")],
                [InlineKeyboardButton("💰 New Deposit", callback_data="new_deposit")]
            ])
            
            await query.edit_message_text(msg, parse_mode='Markdown', reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"❌ Session status error: {e}")
            await query.edit_message_text("❌ Error getting session status.")
    
    async def _refresh_deposit(self, query):
        """Refresh deposit information"""
        try:
            balance = self.wallet_manager.get_wallet_balance(self.main_wallet_address)
            
            msg = f"""
💰 **DEPOSIT STATUS**

**Main Wallet:** `{self.main_wallet_address}`
**Current Balance:** {float(balance):,.6f} SUI
**Required:** {float(self.min_deposit):,} SUI

{'✅ **Ready! Send your token contract address**' if balance >= self.min_deposit else '❌ **Waiting for deposit...**'}

Reply with your token contract address (0x...) when ready.
            """
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Check Balance", callback_data="check_balance")]
            ])
            
            await query.edit_message_text(msg, parse_mode='Markdown', reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"❌ Refresh error: {e}")
            await query.edit_message_text("❌ Error refreshing information.")
    
    def _is_valid_contract_address(self, address: str) -> bool:
        """Validate contract address format (Sui can be 0x2::sui::SUI or 66 chars)"""
        if not address.startswith('0x'):
            return False
            
        return True
    
    def run(self):
        """Start the bot - FIXED INITIALIZATION"""
        try:
            # Create application with proper initialization
            application = Application.builder().token(self.token).build()
            
            # Add handlers
            application.add_handler(CommandHandler("start", self.start))
            application.add_handler(CommandHandler("deposit", self.deposit_command))
            application.add_handler(CommandHandler("status", self.status_command))
            application.add_handler(CommandHandler("help", self.help_command))
            
            application.add_handler(CallbackQueryHandler(self.handle_callback))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
            
            logger.info("🚀 Sui Volume Bot starting...")
            logger.info(f"⚡ Trading Strategy: 70% per trade, 1-minute intervals")
            logger.info(f"💰 Minimum deposit: {self.min_deposit:,} SUI")
            logger.info(f"💸 Fixed fee: {self.fee_amount} SUI")
            
            # Start polling
            application.run_polling(allowed_updates=Update.ALL_TYPES)
            
        except Exception as e:
            logger.error(f"❌ Bot crashed: {e}", exc_info=True)
            raise

def main():
    """Main entry point"""
    try:
        bot = SuiVolumeBot()
        bot.run()
    except KeyboardInterrupt:
        logger.info("⏹️ Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Failed to start bot: {e}", exc_info=True)

if __name__ == '__main__':
    main()