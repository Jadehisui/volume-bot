import { Ed25519Keypair } from '@mysten/sui/keypairs/ed25519';
import { decodeSuiPrivateKey } from '@mysten/sui/cryptography';

try {
    const keyStr = process.argv[2];
    if (!keyStr) throw new Error("No key provided");
    const decoded = decodeSuiPrivateKey(keyStr);
    const kp = Ed25519Keypair.fromSecretKey(decoded.secretKey);
    console.log(JSON.stringify({ address: kp.toSuiAddress() }));
} catch (e) {
    console.error(JSON.stringify({ error: e.message }));
    process.exit(1);
}
