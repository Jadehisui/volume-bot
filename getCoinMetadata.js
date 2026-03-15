
import { getFullnodeUrl, SuiClient } from '@mysten/sui/client';

async function getMetadata(input) {
    const rpcUrl = process.env.RPC_URL || getFullnodeUrl('mainnet');
    const client = new SuiClient({ url: rpcUrl });

    try {
        // 1. If it's already a full type, use it directly
        if (input.includes('::')) {
            const metadata = await client.getCoinMetadata({ coinType: input });
            if (metadata) {
                console.log(JSON.stringify({ success: true, metadata, resolvedType: input }));
                return;
            }
        }

        // 2. If it's just an address, try to discover the coin type
        const packageId = input;
        const modules = await client.getNormalizedMoveModulesByPackage({ package: packageId });

        const possibleTypes = [];
        for (const [modName, mod] of Object.entries(modules)) {
            for (const [structName, struct] of Object.entries(mod.structs)) {
                // Check if the struct name is likely to be a coin (e.g. capitalized, matches mod name, or common names)
                if (struct.abilities.abilities.includes('HasKey') || modName.toLowerCase().includes('coin')) {
                    possibleTypes.push(`${packageId}::${modName}::${structName}`);
                }
            }
        }

        // Try discovered types
        for (const type of possibleTypes) {
            try {
                const metadata = await client.getCoinMetadata({ coinType: type });
                if (metadata) {
                    console.log(JSON.stringify({ success: true, metadata, resolvedType: type }));
                    return;
                }
            } catch (e) {
                // Ignore
            }
        }

        // 3. Last ditch: some common hardcoded fallbacks
        const fallbacks = [`${packageId}::coin::COIN`, `${packageId}::faucet::FAUCET`];
        for (const fallback of fallbacks) {
            try {
                const metadata = await client.getCoinMetadata({ coinType: fallback });
                if (metadata) {
                    console.log(JSON.stringify({ success: true, metadata, resolvedType: fallback }));
                    return;
                }
            } catch (e) {
                // Ignore
            }
        }

        console.log(JSON.stringify({ success: false, error: "Token metadata not found for this address. Please provide the full coin type (e.g. 0x...::coin::COIN)." }));
    } catch (error) {
        console.error(JSON.stringify({ success: false, error: error.message }));
        process.exit(1);
    }
}

const input = process.argv[2];
if (!input) {
    process.exit(1);
}

getMetadata(input);
