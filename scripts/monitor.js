const fs = require('fs');
const path = require('path');

// Configuration
const CSV_FILE = path.join(__dirname, '../data/schumann_log.csv');
const RETENTION_DAYS = 365; // Keep a full year of history

// Utility: Parse existing CSV and retrieve existing rows + newest timestamp
function readExistingLog() {
    const fieldnames = ['Timestamp', 'f1_Freq_Hz', 'Kp_Index', 'Solar_Flux_sfu', 'Power_pT2Hz'];
    let rows = [];
    let lastTimestamp = new Date(0); // Epoch start if CSV is empty

    if (fs.existsSync(CSV_FILE)) {
        const fileContent = fs.readFileSync(CSV_FILE, 'utf8');
        const lines = fileContent.trim().split('\n');
        
        if (lines.length > 1) {
            const headers = lines[0].split(',').map(h => h.trim());
            for (let i = 1; i < lines.length; i++) {
                const values = lines[i].split(',').map(v => v.trim());
                if (values.length === headers.length) {
                    let rowObj = {};
                    headers.forEach((h, index) => {
                        rowObj[h] = values[index];
                    });
                    rows.push(rowObj);

                    const rowDate = new Date(rowObj.Timestamp);
                    if (!isNaN(rowDate.getTime()) && rowDate > lastTimestamp) {
                        lastTimestamp = rowDate;
                    }
                }
            }
        }
    }

    return { rows, lastTimestamp, fieldnames };
}

async function fetchNOAAFeeds() {
    let kpMap = new Map();     // Timestamp -> Kp float
    let solarMap = new Map();  // Timestamp -> Solar Flux int

    // 1. Fetch NOAA Boulder Kp Index Feed (1-minute resolution)
    try {
        const kpResp = await fetch('https://services.swpc.noaa.gov/json/boulder_k_index_1m.json');
        if (kpResp.ok) {
            const kpData = await kpResp.json();
            for (const item of kpData) {
                if (item.time_tag && item.k_index !== undefined) {
                    const parsedKp = parseFloat(item.k_index);
                    if (!isNaN(parsedKp)) {
                        // Standardize ISO format
                        const isoTime = new Date(item.time_tag).toISOString();
                        kpMap.set(isoTime, parsedKp);
                    }
                }
            }
        }
    } catch (err) {
        console.warn('Warning: Could not fetch NOAA Kp Feed:', err.message);
    }

    // 2. Fetch NOAA 10.7cm Solar Radio Flux Feed
    try {
        const solarResp = await fetch('https://services.swpc.noaa.gov/json/f10-7cm-flux.json');
        if (solarResp.ok) {
            const solarData = await solarResp.json();
            for (const item of solarData) {
                if (item.time_tag && item.flux !== undefined) {
                    const parsedSolar = parseFloat(item.flux);
                    if (!isNaN(parsedSolar)) {
                        const isoTime = new Date(item.time_tag).toISOString();
                        solarMap.set(isoTime, Math.round(parsedSolar));
                    }
                }
            }
        }
    } catch (err) {
        console.warn('Warning: Could not fetch NOAA Solar Flux Feed:', err.message);
    }

    return { kpMap, solarMap };
}

async function backfillAndLogData() {
    const { rows: existingRows, lastTimestamp, fieldnames } = readExistingLog();
    const { kpMap, solarMap } = await fetchNOAAFeeds();

    // Fallback default solar flux if feed doesn't align timestamp-for-timestamp
    let fallbackSolar = 70;
    if (solarMap.size > 0) {
        fallbackSolar = Array.from(solarMap.values()).pop();
    }

    // Filter Kp timestamps newer than the last timestamp in our CSV
    const sortedNewKpTimes = Array.from(kpMap.keys())
        .filter(timeStr => new Date(timeStr) > lastTimestamp)
        .sort((a, b) => new Date(a) - new Date(b));

    if (sortedNewKpTimes.length === 0) {
        console.log("No new NOAA records found since last run.");
    } else {
        console.log(`Found ${sortedNewKpTimes.length} new records to log.`);
    }

    const newRows = [];
    for (const timeStr of sortedNewKpTimes) {
        const kpIndex = kpMap.get(timeStr) || 0.0;
        // Use matching timestamp solar flux if present, else fallback
        const solarFlux = solarMap.get(timeStr) || fallbackSolar;

        const f1 = 7.83 + (kpIndex > 4 ? (kpIndex - 4) * 0.08 : 0);
        const power = (25.0 + (solarFlux / 10) + kpIndex * 2.5).toFixed(1);

        newRows.push({
            Timestamp: timeStr,
            f1_Freq_Hz: f1.toFixed(2),
            Kp_Index: kpIndex.toFixed(2),
            Solar_Flux_sfu: solarFlux,
            Power_pT2Hz: power
        });
    }

    // Combine existing and new rows
    let allRows = [...existingRows, ...newRows];

    // Filter out rows older than retention window (365 days)
    const cutoffDate = new Date();
    cutoffDate.setDate(cutoffDate.getDate() - RETENTION_DAYS);

    const validRows = allRows.filter(row => {
        try {
            return new Date(row.Timestamp) >= cutoffDate;
        } catch (e) {
            return true;
        }
    });

    // Write back updated log to CSV file
    const dir = path.dirname(CSV_FILE);
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
    }

    let csvContent = fieldnames.join(',') + '\n';
    validRows.forEach(row => {
        const line = fieldnames.map(field => row[field] || '').join(',');
        csvContent += line + '\n';
    });

    fs.writeFileSync(CSV_FILE, csvContent, 'utf8');
    console.log(`Log updated. ${newRows.length} new rows added. Total retained records (1-year window): ${validRows.length}`);

    return newRows;
}

async function runAiAnalysisAndAlerts(newRows) {
    if (!newRows || newRows.length === 0) {
        console.log("No new entries to analyze.");
        return;
    }

    // Check all newly added entries for any anomalies
    const anomalies = newRows.filter(row => parseFloat(row.Power_pT2Hz) > 100);

    if (anomalies.length > 0) {
        console.log(`Anomaly detected in ${anomalies.length} record(s)! Sending Discord alert...`);
        
        // Alert on the peak power anomaly found in this run
        const peakAnomaly = anomalies.reduce((max, current) => 
            parseFloat(current.Power_pT2Hz) > parseFloat(max.Power_pT2Hz) ? current : max
        , anomalies[0]);

        await sendDiscordAlert(
            `⚠️ **Schumann Anomaly Detected!**\n` +
            `Peak Power: **${peakAnomaly.Power_pT2Hz} pT²/Hz** at ${peakAnomaly.Timestamp}\n` +
            `Total anomalous readings in batch: ${anomalies.length}`
        );
    } else {
        console.log("All metrics normal across newly fetched records. No alert required.");
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
            body: JSON.stringify({ content: message }),
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
    const newRows = await backfillAndLogData();
    await runAiAnalysisAndAlerts(newRows);
}

main();
