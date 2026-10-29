const { Client, GatewayIntentBits, EmbedBuilder } = require('discord.js');

async function runSchumannMonitor() {
    console.log('Fetching live space weather and Schumann data...');

    try {
        // Fetch live NOAA Planetary Kp Index data
        const response = await fetch('https://services.swpc.noaa.gov/json/planetary_k_index_1m.json');
        const data = await response.json();
        
        const latestReading = data[data.length - 1];
        const kpIndex = latestReading ? parseFloat(latestReading.kp_index) : 2.0;

        console.log(`Current Planetary Kp Index: ${kpIndex}`);

        // Define Anomaly Condition (e.g., Kp >= 4.0 triggers an alert)
        const isAnomaly = kpIndex >= 4.0;

        if (isAnomaly) {
            await sendDiscordAlert({
                title: '🚨 Schumann Observatory: Geomagnetic Anomaly Detected',
                description: `High geomagnetic activity detected on live telemetry feeds. Ionospheric D-Layer compression likely.`,
                fields: [
                    { name: 'Planetary Kp Index', value: `${kpIndex} Kp`, inline: true },
                    { name: 'Fundamental (f₁)', value: '7.83 Hz', inline: true },
                    { name: 'Observatory Link', value: 'https://rocketry-team.vercel.app/schumann.html', inline: false }
                ],
                color: 0xFF3366
            });
        } else {
            console.log('All metrics normal. No alert required.');
        }

    } catch (error) {
        console.error('Error monitoring Schumann data:', error);
    }
}

async function sendDiscordAlert(alertData) {
    const token = process.env.DISCORD_BOT_TOKEN;
    if (!token) {
        console.error('Missing DISCORD_BOT_TOKEN environment variable.');
        return;
    }

    const client = new Client({ intents: [GatewayIntentBits.Guilds] });

    client.once('ready', async () => {
        // Automatically finds the first text channel in your server to send the message
        const guild = client.guilds.cache.first();
        if (guild) {
            const channel = guild.channels.cache.find(c => c.isTextBased() && c.permissionsFor(guild.members.me).has('SendMessages'));
            if (channel) {
                const embed = new EmbedBuilder()
                    .setTitle(alertData.title)
                    .setDescription(alertData.description)
                    .addFields(alertData.fields)
                    .setColor(alertData.color)
                    .setTimestamp();

                await channel.send({ embeds: [embed] });
                console.log('Successfully posted alert to Discord!');
            }
        }
        client.destroy();
    });

    await client.login(token);
}

runSchumannMonitor();
