import { SuiClient, getFullnodeUrl } from '@mysten/sui/client';
import { Transaction } from '@mysten/sui/transactions';
import { Ed25519Keypair } from '@mysten/sui/keypairs/ed25519';
import { decodeSuiPrivateKey } from '@mysten/sui/cryptography';
import { AggregatorClient, Env } from '@cetusprotocol/aggregator-sdk';
import BN from 'bn.js';

async function main() {
    try {
        const privateKeyStr = process.argv[2];
        const fromToken = process.argv[3];
        const toToken = process.argv[4];
        const amountStr = process.argv[5]; // in MIST or base token units

        if (!privateKeyStr || !fromToken || !toToken || !amountStr) {
            throw new Error("Usage: node cetusSwap.js <Private_Key> <From_Token> <To_Token> <Amount>");
        }

        const rpcUrl = process.env.RPC_URL || getFullnodeUrl('mainnet');
        const client = new SuiClient({ url: rpcUrl });
        const decoded = decodeSuiPrivateKey(privateKeyStr);
        const keypair = Ed25519Keypair.fromSecretKey(decoded.secretKey);
        const senderAddress = keypair.toSuiAddress();

        // 1. Initialize Cetus SDK Aggregator instance
        const agg = new AggregatorClient(
            'https://api-sui.cetus.zone/router_v2',
            senderAddress,
            client,
            Env.Mainnet
        );

        // 2. Fetch pre-swap router quote
        const routeResult = await agg.findRouters({
            from: fromToken,
            target: toToken,
            amount: new BN(amountStr),
            byAmountIn: true
        });

        if (!routeResult || routeResult.paths.length === 0) {
            throw new Error(`Failed to get route from ${fromToken} to ${toToken}. Insufficient liquidity.`);
        }

        // 3. Construct swap PTB
        const tx = new Transaction();
        await agg.fastRouterSwap({
            router: routeResult,
            txb: tx,
            slippage: 0.005, // 0.5%
        });

        // 4. Sign and execute
        const execRes = await client.signAndExecuteTransaction({
            signer: keypair,
            transaction: tx,
            options: {
                showEffects: true,
                showEvents: true,
                showBalanceChanges: true,
            },
        });

        // Calculate amount out from balance changes
        let amountOut = '0';
        if (execRes.balanceChanges) {
            const tokenChange = execRes.balanceChanges.find(
                (b) => b.coinType === toToken && b.owner.AddressOwner === senderAddress
            );
            if (tokenChange && new BN(tokenChange.amount).gtn(0)) {
                amountOut = tokenChange.amount;
            }
        }

        console.log(JSON.stringify({
            success: execRes.effects?.status?.status === 'success',
            tx_hash: execRes.digest,
            amount_in: amountStr,
            amount_out: amountOut || routeResult.amountOut.toString(),
            error: execRes.effects?.status?.error,
        }));

    } catch (e) {
        console.log(JSON.stringify({ success: false, error: e.message }));
        process.exit(1);
    }
}

main();
