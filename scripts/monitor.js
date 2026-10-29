const fs = require('fs');
const path = require('path');

// Configuration
const CSV_FILE = path.join(__dirname, '../data/schumann_log.csv');
const RETENTION_DAYS = 365; // Keep a full year of history
const API_URL = 'https://rocketry-team.vercel.app/api/path-to-csv'; // Replace with your actual live endpoint

async function fetchCurrentData() {
    try {
        const response = await fetch(API_URL);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return await response.json(); // Assumes your API returns a JSON object with the row data
    } catch (error) {
        console.error("Error fetching data:", error);
        return null;
    }
}

function parseCSVLine(line) {
    // Basic CSV line parser (handles simple comma-separated rows)
    return line.split(',');
}

function updateAndCleanLog(newData) {
    // Ensure the data directory exists
    const dir = path.dirname(CSV_FILE);
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
    }

    const fieldnames = ['Timestamp', 'f1_Freq_Hz', 'Kp_Index', 'Solar_Flux_sfu', 'Power_pT2Hz'];
    let rows = [];

    // 1. Read existing CSV if it exists
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

    // 2. Append the new row if fetched successfully
    if (newData) {
        rows.push({
            Timestamp: newData.Timestamp || new Date().toISOString(),
            f1_Freq_Hz: newData.f1_Freq_Hz || '',
            Kp_Index: newData.Kp_Index || '',
            Solar_Flux_sfu: newData.Solar_Flux_sfu || '',
            Power_pT2Hz: newData.Power_pT2Hz || ''
        });
    }

    // 3. Filter out rows older than 365 days (Rolling Year Window)
    const cutoffDate = new Date();
    cutoffDate.setDate(cutoffDate.getDate() - RETENTION_DAYS);

    const validRows = rows.filter(row => {
        try {
            const rowDate = new Date(row.Timestamp);
            return rowDate >= cutoffDate;
        } catch (e) {
            return true; // Keep row if date parsing fails
        }
    });

    // 4. Write back to CSV
    let csvContent = fieldnames.join(',') + '\n';
    validRows.forEach(row => {
        const line = fieldnames.map(field => row[field] || '').join(',');
        csvContent += line + '\n';
    });

    fs.writeFileSync(CSV_FILE, csvContent, 'utf8');
    console.log(`Log updated. Total retained records (1-year window): ${validRows.length}`);

    // Return latest row for analysis / Discord alerts
    return newData;
}

async function runAiAnalysisAndAlerts(latestData) {
    if (!latestData) return;

    console.log("Analyzing recent Schumann data...");
    
    // Example: Check if power or frequency spikes past a certain threshold to trigger Discord
    // (You can plug your AI logic or threshold checks here)
    const power = parseFloat(latestData.Power_pT2Hz);
    
    if (power > 100) { // Arbitrary threshold example
        console.log("Anomaly detected! Sending Discord alert...");
        await sendDiscordAlert(`⚠️ **Schumann Anomaly Detected!**\nPower: ${power} pT²/Hz at ${latestData.Timestamp}`);
    }
}

async function sendDiscordAlert(message) {
    const token = process.env.DISCORD_BOT_TOKEN;
    if (!token) {
        console.log("Discord token not found, skipping alert.");
        return;
    }
    
    // Add your Discord webhook or bot messaging logic here using discord.js or fetch
    console.log("Alert sent to Discord:", message);
}

async function main() {
    const data = await fetchCurrentData();
    if (data) {
        const latestRow = updateAndCleanLog(data);
        await runAiAnalysisAndAlerts(latestRow);
    }
}

main();
