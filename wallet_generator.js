// wallet_generator.js
import { Ed25519Keypair } from '@mysten/sui/keypairs/ed25519';
import * as bip39 from 'bip39';
import fs from 'fs';
import path from 'path';

function generateWallets(count = 5) {
    const wallets = [];

    for (let i = 0; i < count; i++) {
        // Generate a 12-word mnemonic
        const mnemonic = bip39.generateMnemonic();

        // Derive Ed25519 keypair from the mnemonic using the standard SUI derivation path
        const keypair = Ed25519Keypair.deriveKeypair(mnemonic);
        const address = keypair.toSuiAddress();

        // SUI private key format expected by the bot (suiprivkey...)
        const privateKey = keypair.getSecretKey();

        wallets.push({
            index: i + 1,
            mnemonic,
            address,
            privateKey,
        });
    }

    return wallets;
}

function updateEnvFile(wallets) {
    const envPath = path.resolve(process.cwd(), '.env');
    let envContent = '';

    // Read existing content if it exists
    if (fs.existsSync(envPath)) {
        envContent = fs.readFileSync(envPath, 'utf8');
    } else {
        console.warn('⚠️ .env file not found, creating a new one.');
    }

    console.log('\n📝 Updating .env file with new Sui wallets...\n');

    for (const wallet of wallets) {
        const pkPrefix = `SUB_WALLET_${wallet.index}_PRIVATE_KEY=`;
        const addrPrefix = `SUB_WALLET_${wallet.index}_ADDRESS=`;
        const mnPrefix = `SUB_WALLET_${wallet.index}_MNEMONIC=`;

        const pkLine = `${pkPrefix}${wallet.privateKey}`;
        const addrLine = `${addrPrefix}${wallet.address}`;
        const mnLine = `${mnPrefix}"${wallet.mnemonic}"`;

        // Replace existing lines if present
        if (envContent.includes(pkPrefix)) {
            const regexPk = new RegExp(`^${pkPrefix}.*`, 'm');
            const regexAddr = new RegExp(`^${addrPrefix}.*`, 'm');
            const regexMn = new RegExp(`^${mnPrefix}.*`, 'm');

            envContent = envContent.replace(regexPk, pkLine);
            envContent = envContent.replace(regexAddr, addrLine);

            if (envContent.includes(mnPrefix)) {
                envContent = envContent.replace(regexMn, mnLine);
            } else {
                // If MNEMONIC didn't exist before for this wallet, add it after ADDRESS
                envContent = envContent.replace(regexAddr, `${addrLine}\n${mnLine}`);
            }
        } else {
            // Append if entirely new
            envContent += `\n${pkLine}\n${addrLine}\n${mnLine}\n`;
        }

        console.log(`Wallet #${wallet.index}:`);
        console.log(`Address:  ${wallet.address}`);
        console.log(`Mnemonic: ${wallet.mnemonic}`);
        console.log(`suiprivkey: ${wallet.privateKey}`);
        console.log('-'.repeat(80));
    }

    // Overwrite the file
    fs.writeFileSync(envPath, envContent.trim() + '\n', 'utf8');
}

function main() {
    console.log('='.repeat(80));
    console.log('Generating 5 Sui-Compatible Wallets from Mnemonics');
    console.log('='.repeat(80));
    console.log('⚠️  IMPORTANT SECURITY WARNINGS:');
    console.log('⚠️  These private keys and mnemonics are for educational/testing purposes only');
    console.log('⚠️  Do not use these wallets for real funds on mainnet');
    console.log('⚠️  Never share private keys or mnemonics with anyone');
    console.log('='.repeat(80));
    console.log();

    const wallets = generateWallets(5);
    updateEnvFile(wallets);

    console.log('\n✅ Generated 5 completely new Sui wallets and saved them to .env!');
    console.log('✅ You can import these mnemonics into your Sui Wallet app to view balances.');
}

main();
