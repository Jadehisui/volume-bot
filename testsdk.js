const { initCetusSDK } = require('@cetusprotocol/cetus-sui-clmm-sdk');

console.log(Object.keys(initCetusSDK({ network: 'mainnet' }).Router));
