// ============================================================
// LIMITLESS ROCKETRY — SECURE AI BACKEND
// Vercel Serverless Function
// ============================================================

const ALLOWED_ORIGINS = [
    "https://rocketry-team.vercel.app"
];

const MAX_MESSAGE_LENGTH = 4000;

const MODEL =
    "@cf/meta/llama-3.2-1b-instruct";

export default async function handler(req, res) {

    // --------------------------------------------------------
    // CORS
    // --------------------------------------------------------

    const origin = req.headers.origin;

    if (ALLOWED_ORIGINS.includes(origin)) {
        res.setHeader(
            "Access-Control-Allow-Origin",
            origin
        );
    }

    res.setHeader(
        "Access-Control-Allow-Methods",
        "POST, OPTIONS"
    );

    res.setHeader(
        "Access-Control-Allow-Headers",
        "Content-Type"
    );

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
    // CLOUDFLARE CREDENTIALS
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
    // --------------------------------------------------------

    const prompt = `
You are the central intelligence system of
the Limitless Rocketry AI Laboratory.

Analyze the following research or engineering
mission:

${mission}

You must produce TWO independent analyses.

IMPORTANT:
Return your answer using EXACTLY this format:

ENGINEER:
[engineering analysis]

SCIENTIST:
[scientific analysis]

Do not put either section inside JSON.
Do not combine the two sections.

==================================================

ENGINEER

Act as an aerospace engineer.

Analyze:
- engineering feasibility
- physical principles
- design considerations
- risks and limitations
- useful calculations or measurements
- practical testing approaches

Clearly identify assumptions.

Do not claim that an untested design is safe.

==================================================

SCIENTIST

Act as a research scientist.

Analyze:
- scientific principles
- hypotheses
- independent variables
- dependent variables
- controls
- experimental design
- measurements
- expected observations
- sources of error
- ways to improve the experiment

Clearly distinguish established science
from assumptions or speculation.

Keep both analyses technically useful
and reasonably concise.
`;

    // --------------------------------------------------------
    // CLOUDFLARE AI
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
                        max_tokens: 1200
                    })
                }
            );

        const data =
            await aiResponse.json();

        // ----------------------------------------------------
        // CLOUDFLARE ERROR
        // ----------------------------------------------------

        if (
            !aiResponse.ok ||
            !data.success
        ) {

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
        // GET AI RESPONSE
        // ----------------------------------------------------

        const rawResponse =
            data.result?.response;

        if (
            typeof rawResponse !== "string" ||
            !rawResponse.trim()
        ) {

            return res.status(502).json({
                error:
                    "The AI service returned an empty response."
            });
        }

        // ----------------------------------------------------
        // SEPARATE ENGINEER / SCIENTIST
        // ----------------------------------------------------

        const engineerMarker =
            "ENGINEER:";

        const scientistMarker =
            "SCIENTIST:";

        const engineerStart =
            rawResponse.indexOf(
                engineerMarker
            );

        const scientistStart =
            rawResponse.indexOf(
                scientistMarker
            );

        let engineerResponse =
            "";

        let scientistResponse =
            "";

        if (
            engineerStart !== -1 &&
            scientistStart !== -1 &&
            scientistStart > engineerStart
        ) {

            engineerResponse =
                rawResponse
                    .substring(
                        engineerStart +
                        engineerMarker.length,
                        scientistStart
                    )
                    .trim();

            scientistResponse =
                rawResponse
                    .substring(
                        scientistStart +
                        scientistMarker.length
                    )
                    .trim();

        } else {

            // Fallback if the model does not follow
            // the requested format.

            engineerResponse =
                rawResponse.trim();

            scientistResponse =
                "The scientific analysis could not be separated from the AI response.";
        }

        // ----------------------------------------------------
        // RETURN SEPARATE RESPONSES
        // ----------------------------------------------------

        return res.status(200).json({

            success: true,

            engineer:
                engineerResponse,

            scientist:
                scientistResponse

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
