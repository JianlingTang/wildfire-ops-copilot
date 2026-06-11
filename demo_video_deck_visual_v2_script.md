# Wildfire Ops Copilot - Visual V2 Script

Use `demo_video_deck_visual_v2.pptx` for the video. This deck is intentionally low-text; use the voiceover below for detail.

| Time | Slide | Voiceover |
| --- | --- | --- |
| 0:00-0:15 | Wildfire decisions now happen in minutes | "Wildfire response is now a real-time intelligence problem. Australia's Black Summer burned more than 24 million hectares. In California's 2024 season, CAL FIRE recorded 8,110 wildfires and over 1.07 million acres burned." |
| 0:15-0:35 | Climate pressure | "Climate change does not cause every ignition, but hotter, drier, and windier conditions increase the chance that small ignitions become fast-moving incidents." |
| 0:35-0:55 | The operations gap | "Dispatchers need to react quickly, but the evidence is scattered across hotspot feeds, weather forecasts, warnings, maps, assets, SOPs, and public messaging rules." |
| 0:55-1:12 | AI agent bridge | "An AI agent bridges that gap by gathering evidence, keeping context, explaining risk drivers, and routing reports, scenarios, and actions to the right workflow." |
| 1:12-1:28 | Wildfire Ops Copilot | "Our project is Wildfire Ops Copilot: an emergency-operations dashboard and AI agent for monitoring wildfire activity, analyzing an AOI, and preparing approval-safe actions." |
| 1:28-1:52 | Top features | "The product focuses a live hotspot AOI, generates risk scoring and reports, runs what-if scenarios, and drafts public advisories for human approval." |
| 1:52-2:08 | GCP + Elastic stack | "Firebase hosts the frontend. Cloud Run serves the FastAPI backend. Gemini runs on Vertex AI through Google ADK. Firestore stores runs, reports, alerts, approvals, and trace events. Elastic MCP retrieves operational evidence." |
| 2:08-2:24 | Why Elastic MCP | "Elastic MCP gives the agent searchable operational memory: SOPs, incident history, warning guidance, advisory templates, and reliability notes that can be cited in reports." |
| 2:24-2:53 | Demo flow | "In the demo, we focus an AOI, ask for today's analysis report, inspect the agent trace and risk score, test a wind and humidity scenario, then draft a public advisory that waits for approval." |
| 2:53-3:00 | Explainable action, faster | "Wildfire Ops Copilot turns scattered emergency data into explainable, approval-safe operational intelligence for the next shift briefing." |

## Icon Notes

- Firebase, Google Cloud, and Cloud Run icons were pulled from Iconify's `logos` collection.
- Elastic icon was pulled from Simple Icons.
- Vertex AI and Firestore use the Google Cloud brand icon with service labels because the pulled source did not provide reliable separate service SVGs.
