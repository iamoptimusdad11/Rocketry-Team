const { verifyKey } = require('discord-interactions');

module.exports.config = {
    api: {
        bodyParser: false,
    },
};

async function getRawBody(req) {
    return new Promise((resolve, reject) => {
        let chunks = [];
        req.on('data', (chunk) => chunks.push(chunk));
        req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
        req.on('error', (err) => reject(err));
    });
}

module.exports = async function handler(req, res) {
    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }

    const signature = req.headers['x-signature-ed25519'];
    const timestamp = req.headers['x-signature-timestamp'];
    
    if (!signature || !timestamp) {
        return res.status(401).send('Missing signature headers');
    }

    try {
        const rawBody = await getRawBody(req);

        // CRITICAL: Added 'await' here for the async verifyKey function
        const isVerified = await verifyKey(rawBody, signature, timestamp, process.env.DISCORD_PUBLIC_KEY);
        
        if (!isVerified) {
            return res.status(401).send('Invalid request signature');
        }

        const interaction = JSON.parse(rawBody);

        // 1. Handle Discord PING verification handshake
        if (interaction.type === 1) {
            return res.status(200).json({ type: 1 });
        }

        // 2. Handle Slash Commands (Type 2)
        if (interaction.type === 2) {
            const { name } = interaction.data;

            if (name === 'status') {
                try {
                    const response = await fetch('https://services.swpc.noaa.gov/json/planetary_k_index_1m.json');
                    const data = await response.json();
                    const latest = data[data.length - 1];
                    const kp = latest ? latest.kp_index : '2.0';

                    return res.status(200).json({
                        type: 4,
                        data: {
                            content: `🌍 **Schumann Observatory Live Status**\n- **Planetary Kp Index:** ${kp}\n- **Fundamental Frequency:** 7.83 Hz\n- **Dashboard Link:** https://rocketry-team.vercel.app/schumann.html`
                        }
                    });
                } catch (err) {
                    return res.status(200).json({
                        type: 4,
                        data: { content: '⚠️ Could not retrieve live telemetry feeds right now.' }
                    });
                }
            }

            if (name === 'science') {
                return res.status(200).json({
                    type: 4,
                    data: { content: '⚡ **Schumann Resonances** are global electromagnetic resonances excited by lightning discharges in the Earth-ionosphere cavity, pulsing fundamentally at **7.83 Hz**.' }
                });
            }
        }

        return res.status(400).json({ error: 'Unknown interaction' });

    } catch (err) {
        console.error('Request processing error:', err);
        return res.status(500).send('Internal Server Error');
    }
};
