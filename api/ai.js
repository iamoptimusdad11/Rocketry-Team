// ============================================================
// LIMITLESS ROCKETRY — SECURE AI BACKEND
// Vercel Serverless Function
//
// IMPORTANT:
// No API keys belong in this file.
// Cloudflare credentials are stored in Vercel Environment Variables.
// ============================================================

const ALLOWED_ORIGINS = [
    "https://rocketry-team.vercel.app"
];

// Small request limit to prevent abuse.
const MAX_MESSAGE_LENGTH = 4000;

// Cloudflare Workers AI model.
// We start with a relatively lightweight model to conserve
// the free daily Neuron allocation.
const MODEL = "@cf/meta/llama-3.2-1b-instruct";

export default async function handler(req, res) {

    // --------------------------------------------------------
    // CORS
    // --------------------------------------------------------

    const origin = req.headers.origin;

    if (ALLOWED_ORIGINS.includes(origin)) {
        res.setHeader("Access-Control-Allow-Origin", origin);
    }

    res.setHeader(
        "Access-Control-Allow-Methods",
        "POST, OPTIONS"
    );

    res.setHeader(
        "Access-Control-Allow-Headers",
        "Content-Type"
    );

    // Preflight request
    if (req.method === "OPTIONS") {
        return res.status(204).end();
    }

    // --------------------------------------------------------
    // METHOD CHECK
    // --------------------------------------------------------

    if (req.method !== "POST") {
        return res.status(405).json({
            error: "Method not allowed."
        });
    }

    // --------------------------------------------------------
    // ENVIRONMENT VARIABLES
    // --------------------------------------------------------

    const accountId =
        process.env.CLOUDFLARE_ACCOUNT_ID;

    const apiToken =
        process.env.CLOUDFLARE_API_TOKEN;

    if (!accountId || !apiToken) {

        console.error(
            "Cloudflare environment variables are missing."
        );

        return res.status(500).json({
            error:
                "AI backend is not configured."
        });
    }

    // --------------------------------------------------------
    // REQUEST VALIDATION
    // --------------------------------------------------------

    const body = req.body || {};

    const mission =
        typeof body.mission === "string"
            ? body.mission.trim()
            : "";

    if (!mission) {
        return res.status(400).json({
            error:
                "Mission parameters are required."
        });
    }

    if (
        mission.length >
        MAX_MESSAGE_LENGTH
    ) {
        return res.status(413).json({
            error:
                "Mission parameters are too long."
        });
    }

    // --------------------------------------------------------
    // AI PROMPT
    //
    // One AI request produces two perspectives.
    // This saves free-tier AI usage compared with making
    // two completely independent requests.
    // --------------------------------------------------------

    const prompt = `
You are operating inside the Limitless Rocketry
AI Laboratory.

Analyze the following research or engineering mission:

${mission}

Provide TWO clearly separated analyses.

SECTION 1 — AI ENGINEER

Act as an aerospace engineer.

Focus on:
- engineering feasibility
- physical principles
- design considerations
- risks and limitations
- useful calculations or measurements
- practical testing approaches

Do not pretend that an unverified design is safe.
Identify assumptions clearly.

SECTION 2 — AI SCIENTIST

Act as a research scientist.

Focus on:
- scientific principles
- hypotheses
- variables
- experimental design
- measurements
- expected observations
- possible sources of error
- ways to improve the experiment

Clearly distinguish established principles
from assumptions or speculation.

Keep the response technically useful but concise.
`;

    // --------------------------------------------------------
    // CLOUDFLARE WORKERS AI REQUEST
    // --------------------------------------------------------

    const cloudflareUrl =
        `https://api.cloudflare.com/client/v4/accounts/` +
        `${accountId}/ai/run/${MODEL}`;

    try {

        const aiResponse =
            await fetch(
                cloudflareUrl,
                {
                    method: "POST",

                    headers: {
                        "Authorization":
                            `Bearer ${apiToken}`,

                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({
                        prompt: prompt,

                        // Limit output so the free allocation
                        // isn't consumed unnecessarily.
                        max_tokens: 1200
                    })
                }
            );

        const data =
            await aiResponse.json();

        // ----------------------------------------------------
        // CLOUDFLARE ERROR
        // ----------------------------------------------------

        if (!aiResponse.ok || !data.success) {

            console.error(
                "Cloudflare AI error:",
                data
            );

            return res.status(502).json({
                error:
                    "The AI service could not process the mission."
            });
        }

        // ----------------------------------------------------
        // EXTRACT RESPONSE
        // ----------------------------------------------------

        const response =
            data.result?.response;

        if (
            typeof response !== "string" ||
            !response.trim()
        ) {
            return res.status(502).json({
                error:
                    "The AI service returned an empty response."
            });
        }

        // ----------------------------------------------------
        // RETURN ONLY SAFE DATA TO FRONTEND
        // ----------------------------------------------------

        return res.status(200).json({
            success: true,
            response: response.trim()
        });

    } catch (error) {

        console.error(
            "Backend AI request failed:",
            error
        );

        return res.status(500).json({
            error:
                "Secure AI connection failed."
        });
    }
}
