# database.py - Enhanced with Deposit Detection
import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class SuiDatabase:
    def __init__(self, db_path="sui_bot.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Deposits table - track user deposits with transaction tracking
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS deposits (
                deposit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                token_contract TEXT,
                tx_hash TEXT,
                from_address TEXT,
                status TEXT DEFAULT 'pending', -- pending, processing, completed, failed
                fee_collected BOOLEAN DEFAULT FALSE,
                fee_tx_hash TEXT,
                distributed BOOLEAN DEFAULT FALSE,
                distribution_tx_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Trading sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trading_sessions (
                session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                token_contract TEXT,
                original_amount REAL,
                trading_amount REAL,
                current_balance REAL,
                status TEXT DEFAULT 'active',
                total_trades INTEGER DEFAULT 0,
                total_volume REAL DEFAULT 0,
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Session isolated dynamic wallets
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS session_wallets (
                wallet_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                wallet_index INTEGER,
                address TEXT,
                private_key TEXT,
                mnemonic TEXT,
                FOREIGN KEY (session_id) REFERENCES trading_sessions (session_id)
            )
        ''')
        
        # Trades table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                token_contract TEXT,
                sub_wallet_index INTEGER,
                action TEXT,
                amount REAL,
                price REAL,
                session_id INTEGER,
                tx_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                FOREIGN KEY (session_id) REFERENCES trading_sessions (session_id)
            )
        ''')
        
        # Track processed transactions to avoid duplicates
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_transactions (
                tx_hash TEXT PRIMARY KEY,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Persistent user states
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_states (
                user_id INTEGER PRIMARY KEY,
                pending_ca TEXT,
                state TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ Database initialized successfully")

    def add_user(self, user_id, username):
        """Add user to database if not exists"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username) 
            VALUES (?, ?)
        ''', (user_id, username))
        
        conn.commit()
        conn.close()

    def create_pending_deposit(self, user_id, token_contract):
        """Create a pending deposit record when user confirms"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO deposits (user_id, token_contract, status)
            VALUES (?, ?, 'pending')
        ''', (user_id, token_contract))
        
        deposit_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return deposit_id

    def update_deposit_with_transaction(self, deposit_id, tx_hash, from_address, amount):
        """Update deposit with transaction details when detected"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE deposits 
            SET tx_hash = ?, from_address = ?, amount = ?, status = 'processing'
            WHERE deposit_id = ?
        ''', (tx_hash, from_address, amount, deposit_id))
        
        conn.commit()
        conn.close()

    def mark_deposit_processed(self, deposit_id, fee_tx_hash, distribution_tx_hash):
        """Mark deposit as fully processed"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE deposits 
            SET status = 'completed', fee_collected = TRUE, fee_tx_hash = ?, 
                distributed = TRUE, distribution_tx_hash = ?, processed_at = CURRENT_TIMESTAMP
            WHERE deposit_id = ?
        ''', (fee_tx_hash, distribution_tx_hash, deposit_id))
        
        conn.commit()
        conn.close()

    def get_pending_deposits(self):
        """Get all pending deposits waiting for transactions"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM deposits WHERE status = 'pending'
        ''')
        
        deposits = cursor.fetchall()
        conn.close()
        return deposits

    def get_processing_deposits(self):
        """Get deposits that have transactions but not processed"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM deposits WHERE status = 'processing'
        ''')
        
        deposits = cursor.fetchall()
        conn.close()
        return deposits

    def is_transaction_processed(self, tx_hash):
        """Check if a transaction has already been processed"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) FROM processed_transactions WHERE tx_hash = ?
        ''', (tx_hash,))
        
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0

    def mark_transaction_processed(self, tx_hash):
        """Mark a transaction as processed"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR IGNORE INTO processed_transactions (tx_hash) VALUES (?)
        ''', (tx_hash,))
        
        conn.commit()
        conn.close()

    def create_trading_session(self, user_id, token_contract, original_amount, trading_amount):
        """Start a new trading session for user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO trading_sessions 
            (user_id, token_contract, original_amount, trading_amount, current_balance)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, token_contract, original_amount, trading_amount, trading_amount))
        
        session_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"🆕 Trading session {session_id} for user {user_id}, token {token_contract[:20]}...")
        return session_id

    def store_session_wallets(self, session_id: int, wallets: list):
        """Store the 5 dynamically generated wallets for a specific session"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for w in wallets:
            cursor.execute('''
                INSERT INTO session_wallets 
                (session_id, wallet_index, address, private_key, mnemonic)
                VALUES (?, ?, ?, ?, ?)
            ''', (session_id, w['index'], w['address'], w['private_key'], w['mnemonic']))
            
        conn.commit()
        conn.close()
        logger.info(f"🔐 Stored {len(wallets)} unique wallets for session {session_id}")

    def get_session_wallets(self, session_id: int) -> list:
        """Fetch all dynamically generated sub-wallets for a session"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # To return dict-like objects
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT wallet_index as 'index', address, private_key, mnemonic 
            FROM session_wallets 
            WHERE session_id = ?
            ORDER BY wallet_index ASC
        ''', (session_id,))
        
        wallets = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return wallets

    def record_trade(self, user_id, token_contract, sub_wallet_index, action, amount, price, session_id, tx_hash=None):
        """Record a trade execution"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Record the trade
        cursor.execute('''
            INSERT INTO trades 
            (user_id, token_contract, sub_wallet_index, action, amount, price, session_id, tx_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, token_contract, sub_wallet_index, action, amount, price, session_id, tx_hash))
        
        # Update session balance and volume for BUY trades only
        if action == 'buy':
            cursor.execute('''
                UPDATE trading_sessions 
                SET current_balance = current_balance - ?,
                    total_volume = total_volume + ?,
                    total_trades = total_trades + 1
                WHERE session_id = ? AND status = 'active'
            ''', (amount, amount, session_id))
        
        conn.commit()
        conn.close()

    def get_user_active_sessions(self, user_id):
        """Get all active trading sessions for a user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM trading_sessions 
            WHERE user_id = ? AND status = 'active'
            ORDER BY created_at DESC
        ''', (user_id,))
        
        sessions = cursor.fetchall()
        conn.close()
        return sessions

    def get_all_active_sessions(self):
        """Get all active trading sessions for all users"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM trading_sessions 
            WHERE status = 'active'
        ''')
        
        sessions = cursor.fetchall()
        conn.close()
        return sessions

    def get_session_for_trading(self, session_id):
        """Get session details for trading"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM trading_sessions WHERE session_id = ? AND status = 'active'
        ''', (session_id,))
        
        session = cursor.fetchone()
        conn.close()
        return session

    def mark_session_completed(self, session_id):
        # Mark a session as completed
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE trading_sessions SET status = 'completed', completed_at = ? WHERE session_id = ?",
            (datetime.now(), session_id)
        )
        conn.commit()
        conn.close()
        logger.info(f"✅ Session {session_id} marked as completed")

    def get_user_state(self, user_id):
        """Get persistent user state"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT pending_ca, state FROM user_states WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {'pending_ca': row[0], 'state': row[1]}
        return {}

    def save_user_state(self, user_id, state_dict):
        """Save persistent user state"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        pending_ca = state_dict.get('pending_ca')
        state = state_dict.get('state')
        
        cursor.execute('''
            INSERT INTO user_states (user_id, pending_ca, state, last_updated)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                pending_ca = excluded.pending_ca,
                state = excluded.state,
                last_updated = excluded.last_updated
        ''', (user_id, pending_ca, state, datetime.now()))
        
        conn.commit()
        conn.close()
        logger.info(f"✅ Session {session_id} marked as completed")