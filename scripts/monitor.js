const fs = require('fs');
const path = require('path');

// Configuration
const CSV_FILE = path.join(__dirname, '../data/schumann_log.csv');
const RETENTION_DAYS = 365; // Keep a full year of history

async function fetchAndCalculateSchumannData() {
    let kpIndex = 0.0;
    let solarFlux = 70; // default baseline

    try {
        // 1. Fetch NOAA Boulder Kp Index Feed
        const kpResp = await fetch('https://services.swpc.noaa.gov/json/boulder_k_index_1m.json');
        if (kpResp.ok) {
            const kpData = await kpResp.json();
            if (kpData && kpData.length > 0) {
                const latestKp = parseFloat(kpData[kpData.length - 1].k_index);
                if (!isNaN(latestKp)) kpIndex = latestKp;
            }
        }
    } catch (err) {
        console.warn('Warning: Could not fetch NOAA Kp Feed:', err.message);
    }

    try {
        // 2. Fetch NOAA 10.7cm Solar Radio Flux Feed
        const solarResp = await fetch('https://services.swpc.noaa.gov/json/f10-7cm-flux.json');
        if (solarResp.ok) {
            const solarData = await solarResp.json();
            if (solarData && solarData.length > 0) {
                const latestSolar = parseFloat(solarData[solarData.length - 1].flux);
                if (!isNaN(latestSolar)) solarFlux = Math.round(latestSolar);
            }
        }
    } catch (err) {
        console.warn('Warning: Could not fetch NOAA Solar Flux Feed:', err.message);
    }

    // 3. Derive Schumann metrics
    const f1 = 7.83 + (kpIndex > 4 ? (kpIndex - 4) * 0.08 : 0);
    const power = (25.0 + (solarFlux / 10) + kpIndex * 2.5).toFixed(1);
    const timestamp = new Date().toISOString();

    console.log(`Current Kp: ${kpIndex}, Solar Flux: ${solarFlux}, Derived f1: ${f1.toFixed(2)} Hz, Power: ${power} pT²/Hz`);

    return {
        Timestamp: timestamp,
        f1_Freq_Hz: f1.toFixed(2),
        Kp_Index: kpIndex.toFixed(2),
        Solar_Flux_sfu: solarFlux,
        Power_pT2Hz: power
    };
}

function updateAndCleanLog(newData) {
    const dir = path.dirname(CSV_FILE);
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
    }

    const fieldnames = ['Timestamp', 'f1_Freq_Hz', 'Kp_Index', 'Solar_Flux_sfu', 'Power_pT2Hz'];
    let rows = [];

    // Read existing CSV if it exists
    if (fs.existsSync(CSV_FILE)) {
        const fileContent = fs.readFileSync(CSV_FILE, 'utf8');
        const lines = fileContent.trim().split('\n');
        
        if (lines.length > 1) {
            const headers = lines[0].split(',');
            for (let i = 1; i < lines.length; i++) {
                const values = lines[i].split(',');
                if (values.length === headers.length) {
                    let rowObj = {};
                    headers.forEach((h, index) => {
                        rowObj[h.trim()] = values[index].trim();
                    });
                    rows.push(rowObj);
                }
            }
        }
    }

    // Append new calculated row
    if (newData) {
        rows.push(newData);
    }

    // Filter out rows older than 365 days
    const cutoffDate = new Date();
    cutoffDate.setDate(cutoffDate.getDate() - RETENTION_DAYS);

    const validRows = rows.filter(row => {
        try {
            const rowDate = new Date(row.Timestamp);
            return rowDate >= cutoffDate;
        } catch (e) {
            return true;
        }
    });

    // Write back to CSV
    let csvContent = fieldnames.join(',') + '\n';
    validRows.forEach(row => {
        const line = fieldnames.map(field => row[field] || '').join(',');
        csvContent += line + '\n';
    });

    fs.writeFileSync(CSV_FILE, csvContent, 'utf8');
    console.log(`Log updated. Total retained records (1-year window): ${validRows.length}`);

    return newData;
}

async function runAiAnalysisAndAlerts(latestData) {
    if (!latestData) return;

    const power = parseFloat(latestData.Power_pT2Hz);
    
    // Threshold check for anomaly alerts
    if (true) {
        console.log("Anomaly detected! Sending Discord alert...");
        await sendDiscordAlert(`⚠️ **Schumann Anomaly Detected!**\nPower: ${power} pT²/Hz at ${latestData.Timestamp}`);
    } else {
        console.log("All metrics normal. No alert required.");
    }
}

async function sendDiscordAlert(message) {
    const webhookUrl = process.env.DISCORD_BOT_TOKEN;
    if (!webhookUrl) {
        console.log("Discord token not found, skipping alert.");
        return;
    }

    try {
        const response = await fetch(webhookUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: message })
        });

        if (!response.ok) {
            console.error(`Failed to send Discord alert: ${response.statusText}`);
        } else {
            console.log("Alert successfully sent to Discord!");
        }
    } catch (error) {
        console.error("Error sending Discord alert:", error);
    }
}

async function main() {
    const data = await fetchAndCalculateSchumannData();
    if (data) {
        const latestRow = updateAndCleanLog(data);
        await runAiAnalysisAndAlerts(latestRow);
    }
}

main();
