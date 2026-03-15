
import { getFullnodeUrl, SuiClient } from '@mysten/sui/client';

async function getMetadata(coinType) {
    const rpcUrl = process.env.RPC_URL || getFullnodeUrl('mainnet');
    const client = new SuiClient({ url: rpcUrl });

    try {
        const metadata = await client.getCoinMetadata({ coinType });
        console.log(JSON.stringify({ success: true, metadata }));
    } catch (error) {
        console.error(JSON.stringify({ success: false, error: error.message }));
        process.exit(1);
    }
}

const coinType = process.argv[2];
if (!coinType) {
    console.error(JSON.stringify({ success: false, error: "No coin type provided" }));
    process.exit(1);
}

getMetadata(coinType);
