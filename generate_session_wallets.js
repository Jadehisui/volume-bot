// generate_session_wallets.js
import { Ed25519Keypair } from '@mysten/sui/keypairs/ed25519';
import * as bip39 from 'bip39';

function generateWallets(count = 5) {
    const wallets = [];

    for (let i = 0; i < count; i++) {
        // Generate a 12-word mnemonic
        const mnemonic = bip39.generateMnemonic();

        // Derive Ed25519 keypair from the mnemonic using the standard SUI derivation path
        const keypair = Ed25519Keypair.deriveKeypair(mnemonic);
        const address = keypair.toSuiAddress();

        // SUI private key format expected by the bot (suiprivkey...)
        const privateKey = keypair.getSecretKey();

        wallets.push({
            index: i + 1,
            mnemonic,
            address,
            privateKey,
        });
    }

    return wallets;
}

function main() {
    try {
        const count = process.argv[2] ? parseInt(process.argv[2], 10) : 5;
        const wallets = generateWallets(count);

        // Output raw JSON for the python subprocess to parse easily
        console.log(JSON.stringify({
            success: true,
            wallets: wallets
        }));
    } catch (error) {
        console.log(JSON.stringify({
            success: false,
            error: error.message
        }));
        process.exit(1);
    }
}

main();
