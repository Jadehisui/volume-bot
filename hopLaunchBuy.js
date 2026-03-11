import { SuiClient, getFullnodeUrl } from '@mysten/sui/client';
import { Transaction } from '@mysten/sui/transactions';
import { Ed25519Keypair } from '@mysten/sui/keypairs/ed25519';
import { decodeSuiPrivateKey } from '@mysten/sui/cryptography';

// ─── Hop Launchpad On-Chain Config ───────────────────────────────────────────
// Verified from hop.fun frontend bundle (index-iHT6mDIE.js) on 2026-03-11
// Update if the package/config objects change after a protocol upgrade.
const HOPLAUNCH_PACKAGE = '0x3b2612ad888338fb054bd485513095646a0c113b2d491fcc6feba46db0967aa3';
const HOPV4_CONFIG = '0x1e9e187c0877b6cf059370259b24ac6a7733961f69dfbdc8ffd808815521b377';
const DYNAMIC_FEE = '0x3bc5dd26cb2e4215623d4c0fd51376bf660c119d0a57b2e0db0b7294e46c26ca';
const HOPLAUNCH_CONFIG = '0xbb8d6f6e4f6a3b11965dc4c3aa487f0d3b98a6f458f2a98b00fab05fc34c0297';

// SUI coin type (native gas token)
const SUI_COIN_TYPE = '0x2::sui::SUI';

/**
 * Buy tokens on the Hop Launchpad bonding curve.
 *
 * CLI args:
 *   1. privateKey  – suiprivkey... encoded Ed25519 key
 *   2. curveId     – the bonding curve object ID for the token
 *   3. coinType    – fully-qualified Move type of the token, e.g.
 *                    "0xabc::mytoken::MYTOKEN"
 *   4. amountSui   – SUI to spend, in MIST (1 SUI = 1_000_000_000 MIST)
 *   5. minAmountOut – (optional) minimum tokens out, default 0
 *
 * Stdout: JSON { success, tx_hash, amount_in, amount_out, error }
 */
async function main() {
    try {
        const privateKeyStr = process.argv[2];
        const curveId = process.argv[3];
        const coinType = process.argv[4];
        const amountStr = process.argv[5];
        const minOut = process.argv[6] ? BigInt(process.argv[6]) : 0n;

        if (!privateKeyStr || !curveId || !coinType || !amountStr) {
            throw new Error(
                'Usage: node hopLaunchBuy.js <privateKey> <curveId> <coinType> <amountMist> [minAmountOut]'
            );
        }

        const amount = BigInt(amountStr);

        // ── Client + signer setup ────────────────────────────────────────────
        const rpcUrl = process.env.RPC_URL || getFullnodeUrl('mainnet');
        const client = new SuiClient({ url: rpcUrl });

        const decoded = decodeSuiPrivateKey(privateKeyStr);
        const keypair = Ed25519Keypair.fromSecretKey(decoded.secretKey);
        const sender = keypair.toSuiAddress();

        // ── Build PTB ────────────────────────────────────────────────────────
        const tx = new Transaction();
        tx.setSender(sender);

        // Split exact SUI amount from the gas coin
        const [coin] = tx.splitCoins(tx.gas, [tx.pure.u64(amount)]);

        tx.moveCall({
            target: `${HOPLAUNCH_PACKAGE}::curve::buy`,
            typeArguments: [coinType],
            arguments: [
                tx.object(HOPV4_CONFIG),
                tx.object(DYNAMIC_FEE),
                tx.object(curveId),
                tx.object(HOPLAUNCH_CONFIG),
                coin,
                tx.pure.u64(minOut),   // min amount out (slippage guard)
            ],
        });

        // ── Execute ──────────────────────────────────────────────────────────
        const execRes = await client.signAndExecuteTransaction({
            signer: keypair,
            transaction: tx,
            options: {
                showEffects: true,
                showEvents: true,
                showBalanceChanges: true,
            },
        });

        const status = execRes.effects?.status?.status;

        // Derive received token amount from balance changes
        let amountOut = '0';
        if (execRes.balanceChanges) {
            const tokenChange = execRes.balanceChanges.find(
                (b) =>
                    b.coinType === coinType &&
                    b.owner?.AddressOwner === sender &&
                    BigInt(b.amount) > 0n
            );
            if (tokenChange) {
                amountOut = tokenChange.amount;
            }
        }

        console.log(JSON.stringify({
            success: status === 'success',
            tx_hash: execRes.digest,
            amount_in: amountStr,
            amount_out: amountOut,
            error: execRes.effects?.status?.error ?? null,
        }));

    } catch (e) {
        console.log(JSON.stringify({ success: false, error: e.message }));
        process.exit(1);
    }
}

main();
