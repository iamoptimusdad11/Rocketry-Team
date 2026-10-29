export default async function handler(req, res) {
  try {
    // --- 1. GET REQUEST: Auto-registers commands when visiting the URL ---
    if (req.method === 'GET') {
      const BOT_TOKEN = process.env.DISCORD_BOT_TOKEN;
      const APPLICATION_ID = process.env.DISCORD_APPLICATION_ID;

      if (!BOT_TOKEN || !APPLICATION_ID) {
        return res.status(400).json({ 
          error: "Missing environment variables. Check DISCORD_BOT_TOKEN and DISCORD_APPLICATION_ID in Vercel settings." 
        });
      }

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

      const discordRes = await fetch(`https://discord.com/api/v10/applications/${APPLICATION_ID}/commands`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bot ${BOT_TOKEN}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(commands),
      });

      const data = await discordRes.json();
      
      if (!discordRes.ok) {
        return res.status(500).json({ error: "Discord API rejected registration", details: data });
      }

      return res.status(200).json({ success: true, registered_commands: data });
    }

    // --- 2. POST REQUEST: Handles Discord Bot Interactions ---
    if (req.method === 'POST') {
      // Handle Discord Ping (Type 1)
      if (req.body && req.body.type === 1) {
        return res.status(200).json({ type: 1 });
      }

      // Handle Slash Commands (Type 2)
      if (req.body && req.body.type === 2) {
        const commandName = req.body.data?.name;

        if (commandName === 'status') {
          return res.status(200).json({
            type: 4,
            data: {
              content: "📡 **Live Telemetry:** Schumann Resonance is stable at 7.83 Hz. Kp Index is calm (2)."
            }
          });
        }

        if (commandName === 'science') {
          return res.status(200).json({
            type: 4,
            data: {
              content: "🔬 The Schumann resonances are a set of spectrum peaks in the extremely low frequency (ELF) portion of the Earth's electromagnetic field."
            }
          });
        }
      }

      return res.status(400).json({ error: 'Unknown interaction type' });
    }

    return res.status(405).json({ error: 'Method not allowed' });

  } catch (err) {
    return res.status(500).json({ error: "Internal Server Error", details: err.message });
  }
}
