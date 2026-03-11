import { SuiClient, getFullnodeUrl } from '@mysten/sui/client';
import { Transaction } from '@mysten/sui/transactions';
import { Ed25519Keypair } from '@mysten/sui/keypairs/ed25519';
import { decodeSuiPrivateKey } from '@mysten/sui/cryptography';

// ─── Hop Launchpad On-Chain Config ───────────────────────────────────────────
// Verified from hop.fun frontend bundle (index-iHT6mDIE.js) on 2026-03-11
const HOPLAUNCH_PACKAGE = '0x3b2612ad888338fb054bd485513095646a0c113b2d491fcc6feba46db0967aa3';
const HOPV4_CONFIG = '0x1e9e187c0877b6cf059370259b24ac6a7733961f69dfbdc8ffd808815521b377';
const DYNAMIC_FEE = '0x3bc5dd26cb2e4215623d4c0fd51376bf660c119d0a57b2e0db0b7294e46c26ca';
const HOPLAUNCH_CONFIG = '0xbb8d6f6e4f6a3b11965dc4c3aa487f0d3b98a6f458f2a98b00fab05fc34c0297';

/**
 * Sell tokens back to SUI on the Hop Launchpad bonding curve.
 *
 * CLI args:
 *   1. privateKey   – suiprivkey... encoded Ed25519 key
 *   2. curveId      – the bonding curve object ID for the token
 *   3. coinType     – fully-qualified Move type, e.g. "0xabc::mytoken::MYTOKEN"
 *   4. tokenAmount  – exact token amount (in base units) to sell
 *   5. minSuiOut    – (optional) minimum SUI out, default 0
 *
 * Stdout: JSON { success, tx_hash, token_amount_in, sui_received, error }
 */
async function main() {
    try {
        const privateKeyStr = process.argv[2];
        const curveId = process.argv[3];
        const coinType = process.argv[4];
        const tokenAmountStr = process.argv[5];
        const minSuiOut = process.argv[6] ? BigInt(process.argv[6]) : 0n;

        if (!privateKeyStr || !curveId || !coinType || !tokenAmountStr) {
            throw new Error(
                'Usage: node hopLaunchSell.js <privateKey> <curveId> <coinType> <tokenAmount> [minSuiOut]'
            );
        }

        const tokenAmount = BigInt(tokenAmountStr);

        // ── Client + signer ──────────────────────────────────────────────────
        const rpcUrl = process.env.RPC_URL || getFullnodeUrl('mainnet');
        const client = new SuiClient({ url: rpcUrl });

        const decoded = decodeSuiPrivateKey(privateKeyStr);
        const keypair = Ed25519Keypair.fromSecretKey(decoded.secretKey);
        const sender = keypair.toSuiAddress();

        // ── Find the token coin object to sell ───────────────────────────────
        // We need a coin object of the right type owned by the sender
        const { data: coins } = await client.getCoins({
            owner: sender,
            coinType: coinType,
        });

        if (!coins || coins.length === 0) {
            throw new Error(`No ${coinType} coins found in wallet ${sender}`);
        }

        // Pick the coin with the largest balance (or exact match)
        coins.sort((a, b) => Number(BigInt(b.balance) - BigInt(a.balance)));
        const sellCoinObj = coins[0];

        // ── Build PTB ────────────────────────────────────────────────────────
        const tx = new Transaction();
        tx.setSender(sender);

        let sellCoin;
        const coinBalance = BigInt(sellCoinObj.balance);

        if (coinBalance === tokenAmount) {
            // Use the entire coin directly
            sellCoin = tx.object(sellCoinObj.coinObjectId);
        } else {
            // Split exact amount from the largest coin
            const [split] = tx.splitCoins(tx.object(sellCoinObj.coinObjectId), [
                tx.pure.u64(tokenAmount),
            ]);
            sellCoin = split;
        }

        tx.moveCall({
            target: `${HOPLAUNCH_PACKAGE}::curve::sell`,
            typeArguments: [coinType],
            arguments: [
                tx.object(HOPV4_CONFIG),
                tx.object(DYNAMIC_FEE),
                tx.object(curveId),
                tx.object(HOPLAUNCH_CONFIG),
                sellCoin,
                tx.pure.u64(minSuiOut),  // min SUI out (slippage guard)
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

        // Derive SUI received from balance changes
        let suiReceived = '0';
        if (execRes.balanceChanges) {
            const suiChange = execRes.balanceChanges.find(
                (b) =>
                    b.coinType === '0x2::sui::SUI' &&
                    b.owner?.AddressOwner === sender &&
                    BigInt(b.amount) > 0n
            );
            if (suiChange) {
                suiReceived = suiChange.amount;
            }
        }

        console.log(JSON.stringify({
            success: status === 'success',
            tx_hash: execRes.digest,
            token_amount_in: tokenAmountStr,
            sui_received: suiReceived,
            error: execRes.effects?.status?.error ?? null,
        }));

    } catch (e) {
        console.log(JSON.stringify({ success: false, error: e.message }));
        process.exit(1);
    }
}

main();
