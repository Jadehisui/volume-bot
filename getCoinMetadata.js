import { SuiClient, getFullnodeUrl } from '@mysten/sui/client';

async function main() {
    const coinType = process.argv[2];
    if (!coinType) {
        console.error(JSON.stringify({ success: false, error: 'No coin type provided' }));
        process.exit(1);
    }

    const rpcUrl = process.env.RPC_URL || getFullnodeUrl('mainnet');
    const client = new SuiClient({ url: rpcUrl });

    try {
        const metadata = await client.getCoinMetadata({ coinType });
        if (metadata) {
            console.log(JSON.stringify({
                success: true,
                metadata: {
                    name: metadata.name,
                    symbol: metadata.symbol,
                    decimals: metadata.decimals,
                    description: metadata.description,
                    iconUrl: metadata.iconUrl,
                    id: metadata.id
                },
                resolvedType: coinType
            }));
        } else {
            // Some coins might not have metadata but still exist or just have a symbol
            console.log(JSON.stringify({
                success: true,
                metadata: {
                    name: "Unknown Token",
                    symbol: coinType.split('::').pop(),
                    decimals: 9
                },
                resolvedType: coinType
            }));
        }
    } catch (error) {
        console.error(JSON.stringify({ success: false, error: error.message }));
        process.exit(1);
    }
}

main();
