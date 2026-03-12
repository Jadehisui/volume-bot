import os
import subprocess
from decimal import Decimal
from pysui import SuiConfig, SyncClient
from pysui.sui.sui_crypto import keypair_from_keystring

def test_pysui_methods():
    
    # Let's generate a valid keystring using suikey command (if it exists) or sui CLI.
    # Actually I can just write the test to test the JS script to generate the keys OR do a small loop.
    res = subprocess.run(["node", "-e", "import { Ed25519Keypair } from '@mysten/sui/keypairs/ed25519'; const kp = new Ed25519Keypair(); console.log(kp.getSecretKey().toString(), kp.toSuiAddress());"], text=True, capture_output=True)
    print("JS Gen:", res.stdout)
    
if __name__ == '__main__':
    test_pysui_methods()
