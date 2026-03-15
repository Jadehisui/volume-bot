
import os
import sys
import asyncio
from decimal import Decimal
from wallet_manager import WalletManager
from database import SuiDatabase

async def main():
    db = SuiDatabase()
    wm = WalletManager(db)
    
    user_id = 99999
    token_contract = "0xab0cf2644867272bc89a77d9cff0633e3d50e3f738b963d9c8e6899b529803a8::capy::CAPY"
    current_balance = Decimal("20.0")
    trading_amount = Decimal("18.0")
    
    print(f"--- Testing Wallet Generation ---")
    try:
        session_id = db.create_trading_session(user_id, token_contract, float(current_balance), float(trading_amount))
        print(f"Created session {session_id}")
        
        print(f"Calling generate_session_wallets...")
        wallets = wm.generate_session_wallets(session_id, count=5)
        
        if not wallets:
            print(f"FAIL: generate_session_wallets returned empty list")
        elif len(wallets) != 5:
            print(f"FAIL: generate_session_wallets returned {len(wallets)} wallets instead of 5")
        else:
            print(f"SUCCESS: Generated 5 wallets for session {session_id}")
            for w in wallets:
                print(f"  Wallet {w['index']}: {w['address']}")
                
    except Exception as e:
        print(f"EXCEPTION: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
