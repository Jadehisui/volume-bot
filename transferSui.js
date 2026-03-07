import { getFullnodeUrl, SuiClient } from '@mysten/sui/client';
import { Transaction } from '@mysten/sui/transactions';
import { Ed25519Keypair } from '@mysten/sui/keypairs/ed25519';
import { decodeSuiPrivateKey } from '@mysten/sui/cryptography';

async function main() {
    const fromKeyStr = process.argv[2];
    const toAddress = process.argv[3];
    const amountFloat = parseFloat(process.argv[4]);
    const rpcUrl = process.env.RPC_URL || getFullnodeUrl('mainnet');

    try {
        if (!fromKeyStr || !toAddress || isNaN(amountFloat)) {
            throw new Error("Missing arguments: node transferSui.js <key> <to> <amount>");
        }

        const client = new SuiClient({ url: rpcUrl });

        let keypair;
        try {
            if (fromKeyStr.startsWith('suiprivkey')) {
                const decoded = decodeSuiPrivateKey(fromKeyStr);
                keypair = Ed25519Keypair.fromSecretKey(decoded.secretKey);
            } else {
                console.error(JSON.stringify({ success: false, error: 'Expected suiprivkey prefix' }));
                process.exit(1);
            }
        } catch (e) {
            console.error(JSON.stringify({ success: false, error: 'Failed to decode key: ' + e.message }));
            process.exit(1);
        }

        const amountMist = Math.floor(amountFloat * 1_000_000_000);

        const tx = new Transaction();
        const [coin] = tx.splitCoins(tx.gas, [amountMist]);
        tx.transferObjects([coin], toAddress);

        const result = await client.signAndExecuteTransaction({
            transaction: tx,
            signer: keypair,
            options: { showEffects: true, showEvents: true }
        });

        console.log(JSON.stringify({
            success: result.effects?.status?.status === 'success',
            tx_hash: result.digest,
            error: result.effects?.status?.error,
            amount: amountFloat,
            description: process.argv[5] || ""
        }));
    } catch (error) {
        console.error(JSON.stringify({ success: false, error: error.message }));
        process.exit(1);
    }
}

main();
