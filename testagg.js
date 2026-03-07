import { AggregatorClient, Env } from '@cetusprotocol/aggregator-sdk';
import { SuiClient, getFullnodeUrl } from '@mysten/sui/client';

async function test() {
    const client = new SuiClient({ url: getFullnodeUrl('mainnet') });
    const agg = new AggregatorClient('https://api-sui.cetus.zone/router/v2', '0x164fb4ef5a2dc70a9fa3d02bfa4e3f36072110c73e9702ccb72ebf44358ce245', client, Env.Mainnet);

    const fromToken = '0x2::sui::SUI';
    const toToken = '0x5d4b302506645c37ff133b98c4b50a5ae14841659738d6d733d59d0d217a91dd::wusdc::WUSDC';
    const amountStr = '10000000'; // 0.01 SUI

    console.log("Fetching route...");
    try {
        const route = await agg.findRouting({
            from: fromToken,
            to: toToken,
            amount: amountStr,
            exactIn: true
        });

        console.log("Route Found:", JSON.stringify(route, null, 2));
    } catch (e) {
        console.error("Error finding route:", e);
    }
}

test();
