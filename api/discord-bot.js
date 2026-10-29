import { verifyKey } from 'discord-interactions';

export default async function handler(req, res) {
    if (req.method !== 'POST') {
        return res.status(405).json({ error: 'Method not allowed' });
    }

    // Verify cryptographic signature from Discord to ensure security
    const signature = req.headers['x-signature-ed25519'];
    const timestamp = req.headers['x-signature-timestamp'];
    const rawBody = JSON.stringify(req.body);

    const isVerified = verifyKey(rawBody, signature, timestamp, process.env.DISCORD_PUBLIC_KEY);
    if (!isVerified) {
        return res.status(401).send('Invalid request signature');
    }

    const interaction = req.body;

    // 1. Handle Discord PING verification handshake
    if (interaction.type === 1) {
        return res.status(200).json({ type: 1 });
    }

    // 2. Handle Slash Commands (Type 2)
    if (interaction.type === 2) {
        const { name, options } = interaction.data;

        // Command: /status
        if (name === 'status') {
            try {
                const response = await fetch('https://services.swpc.noaa.gov/json/planetary_k_index_1m.json');
                const data = await response.json();
                const latest = data[data.length - 1];
                const kp = latest ? latest.kp_index : '2.0';

                return res.status(200).json({
                    type: 4, // Channel message with source
                    data: {
                        content: `🌍 **Schumann Observatory Live Status**\n- **Planetary Kp Index:** ${kp}\n- **Fundamental Frequency ($f_1$):** 7.83 Hz\n- **Ionosphere D-Layer Height:** 68.2 km\n- **Dashboard Link:** https://rocketry-team.vercel.app/schumann.html`
                    }
                });
            } catch (err) {
                return res.status(200).json({
                    type: 4,
                    data: { content: '⚠️ Could not retrieve live telemetry feeds right now.' }
                });
            }
        }

        // Command: /science [topic]
        if (name === 'science') {
            const topicOption = options?.find(opt => opt.name === 'topic')?.value || 'schumann';
            
            let explanation = '';
            if (topicOption === 'schumann') {
                explanation = '⚡ **Schumann Resonances** are global electromagnetic resonances excited by lightning discharges in the cavity bounded by Earth\'s surface and the ionosphere. The fundamental mode is **7.83 Hz** (often called Earth\'s heartbeat). In rocketry and atmospheric research, shifts in these frequencies help monitor D-layer ionization and solar flare disruptions!';
            } else if (topicOption === 'kp') {
                explanation = '🌌 **Planetary K-index** quantifies disturbances in the horizontal component of Earth\'s magnetic field with an integer from 0 to 9. Values $\\ge 4$ indicate active geomagnetic conditions that can compress the ionosphere and affect high-altitude radio telemetry.';
            } else {
                explanation = '🚀 **Rocketry & Space Weather:** High-altitude rocket payloads rely on stable radio propagation. Solar storms, coronal mass ejections (CMEs), and geomagnetic fluctuations directly alter ionospheric density, impacting RF communication links.';
            }

            return res.status(200).json({
                type: 4,
                data: { content: explanation }
            });
        }
    }

    return res.status(400).json({ error: 'Unknown interaction' });
}
