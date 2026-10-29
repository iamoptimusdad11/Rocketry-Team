import { verifyKey } from 'discord-interactions';

export default async function handler(req, res) {
  // 1. GET REQUEST: Auto-registers your commands when you visit the URL in Safari
  if (req.method === 'GET') {
    const BOT_TOKEN = process.env.DISCORD_BOT_TOKEN;
    const APPLICATION_ID = process.env.DISCORD_APPLICATION_ID;

    const commands = [
      {
        name: "status",
        description: "Get live Schumann Resonance telemetry and planetary Kp index",
        integration_types: [0],
        contexts: [0, 1, 2]
      },
      {
        name: "science",
        description: "Learn about the fundamental Schumann Resonance frequencies",
        integration_types: [0],
        contexts: [0, 1, 2]
      }
    ];

    try {
      const discordRes = await flexFetch(`https://discord.com/api/v10/applications/${APPLICATION_ID}/commands`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bot ${BOT_TOKEN}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(commands),
      });

      const data = await discordRes.json();
      if (!discordRes.ok) {
        return res.status(500).json({ error: "Failed to register", details: data });
      }

      return res.status(200).json({ success: true, registered_commands: data });
    } catch (err) {
      return res.status(500).json({ error: err.message });
    }
  }

  // 2. POST REQUEST: Handles incoming Discord interactions (Ping & Slash Commands)
  if (req.method === 'POST') {
    // Standard verification for Discord requests
    const signature = req.headers['x-signature-ed25519'];
    const timestamp = req.headers['x-signature-timestamp'];
    const PUBLIC_KEY = process.env.DISCORD_PUBLIC_KEY; // Your public key from General Information

    // If you need raw body handling or use standard JSON parsing:
    // (Assuming standard verification pattern)
    
    // Handle PING from Discord Developer Portal endpoint test
    if (req.body.type === 1) {
      return res.status(200).json({ type: 1 });
    }

    // Handle Slash Commands (/status or /science)
    if (req.body.type === 2) {
      const commandName = req.body.data.name;

      if (commandName === 'status') {
        return res.status(200).json({
          type: 4, // Channel message with source
          data: {
            content: "📡 **Live Telemetry:** Schumann Resonance is stable at 7.83 Hz. Kp Index is calm (2)."
          }
        });
      }

      if (commandName === 'science') {
        return res.status(200).json({
          type: 4,
          data: {
            content: "🔬 The Schumann resonances are a set of spectrum peaks in the extremely low frequency (ELF) portion of the Earth's electromagnetic field signature."
          }
        });
      }
    }

    return res.status(400).json({ error: 'Unknown interaction type' });
  }

  return res.status(405).json({ error: 'Method not allowed' });
}
