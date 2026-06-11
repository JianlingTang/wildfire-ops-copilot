# Wildfire Ops Copilot - 3 Minute Demo Video Deck

## Video Goal

Show why wildfire operations need an AI-assisted workflow, then demonstrate how Wildfire Ops Copilot turns live hotspot, weather, warning, spatial, and Elastic MCP evidence into an operational report, scenario answer, and approval-gated public advisory.

## Timeline

| Time | Slide | Visual / Animation Direction | Voiceover Script |
| --- | --- | --- | --- |
| 0:00-0:15 | 1. Opening Hook | Fast montage: satellite fire map, orange smoke overlay, two large stat callouts. | "Wildfire response is becoming a real-time data problem. Australia's Black Summer showed the scale: over 24 million hectares burned and 33 direct deaths. In California's 2024 season, CAL FIRE recorded 8,110 wildfires and more than 1.07 million acres burned." |
| 0:15-0:35 | 2. Climate Pressure | Animate three drivers in: heat, drought, wind. | "Climate change does not create every ignition, but hotter and drier conditions increase the chance that small ignitions become fast-moving incidents. For responders, the window to understand risk is shrinking." |
| 0:35-0:55 | 3. The Operations Gap | Split screen: dispatcher dashboard chaos vs. clean decision timeline. | "Dispatchers and operations analysts need to react quickly, but the evidence is scattered: satellite hotspots, weather forecasts, warnings, spatial exposure, historical incidents, SOPs, and public communication rules. Much of it is geospatial, time-sensitive, and hard to compare under pressure." |
| 0:55-1:12 | 4. AI Agent Bridge | Flow animation: many data sources into one agent, then decision outputs. | "An AI agent can bridge that gap by continuously gathering evidence, preserving context, explaining risk drivers, and routing each request to the right workflow. The goal is not to replace incident commanders. It is to reduce the time from raw signals to defensible action." |
| 1:12-1:28 | 5. Project Goal | Product name appears first, then one sentence goal. | "Our project is Wildfire Ops Copilot: an emergency-operations dashboard and AI agent for wildfire monitoring, AOI analysis, recommendations, report generation, and human-approved advisory drafting." |
| 1:28-1:52 | 6. Top Features | Three feature cards animate one by one. | "The first feature is live AOI focus from Australian hotspot activity. The second is agent-driven analysis that combines weather, hotspots, warnings, exposure, and Elastic evidence into a risk score and report. The third is operational follow-through: what-if scenarios, inspection priorities, and public advisory drafts that stay behind human approval." |
| 1:52-2:08 | 7. Tech Stack | Icon cascade: Firebase, Cloud Run, FastAPI, Vertex AI/Gemini, ADK, Elastic MCP, Firestore. | "The stack is built on Google Cloud and Elastic. Firebase hosts the frontend. Cloud Run serves the FastAPI backend. Vertex AI runs Gemini through the Google ADK agent runtime. Firestore stores runs, reports, alerts, approvals, and trace events. Elastic Agent Builder MCP retrieves operational evidence from our wildfire knowledge index." |
| 2:08-2:24 | 8. Why Elastic MCP | Zoom into knowledge index: SOPs, historical incidents, warning guidance, advisory templates. | "Elastic MCP matters because the agent needs more than live sensor data. It needs trusted operational memory: policies, SOPs, historical patterns, warning guidance, advisory templates, and data reliability notes. Elastic makes that searchable as a tool the agent can cite." |
| 2:24-2:53 | 9. Live Demo Flow | Screen recording: hosted dashboard. Show map focus, chat prompt, trace, report, what-if, advisory draft. | "In the demo, we open the dashboard, focus an area of interest, and ask: analyze this region and generate today's report. The agent gathers hotspot, weather, warning, spatial, and Elastic evidence, computes risk, and generates a report. Then we ask a what-if scenario: wind up 30 percent and humidity down 10 percent. Finally, we ask it to draft a public advisory, which is saved for approval instead of being sent automatically." |
| 2:53-3:00 | 10. Closing | Final product screen with tagline. | "Wildfire Ops Copilot turns scattered emergency data into explainable, approval-safe operational intelligence, fast enough for the next shift briefing." |

## Slide Content

### 1. Opening Hook

**Title:** Wildfire response is now a real-time intelligence problem

- Australia Black Summer: 24M+ hectares burned
- California 2024: 8,110 wildfires, 1,077,711 acres burned
- The question: can operators move from signal to action faster?

### 2. Climate Pressure

**Title:** The risk window is getting tighter

- Hotter conditions dry fuels faster
- Drought and low humidity amplify spread
- Wind shifts can change priorities within minutes

### 3. The Operations Gap

**Title:** Dispatchers face a data overload problem

- Many sources: hotspots, weather, warnings, maps, assets, SOPs
- Spatial data is hard to compare quickly
- Evidence changes continuously during an incident
- Public messaging must be accurate and approved

### 4. AI Agent Bridge

**Title:** AI bridges raw signals and operational decisions

- Gather multi-source evidence
- Keep incident context across requests
- Explain risk drivers and uncertainty
- Route reports, scenarios, and actions to the right workflow

### 5. Project Goal

**Title:** Wildfire Ops Copilot

**Goal:** Help emergency operators monitor wildfire activity, analyze an AOI, generate explainable recommendations, and prepare approval-gated public communications.

### 6. Top Features

**Title:** What the product does

1. Live hotspot map and AOI focus
2. Agent analysis with risk scoring and reports
3. What-if scenarios, inspection priorities, and approval-safe advisory drafts

### 7. Tech Stack

**Title:** Built on GCP + Elastic

- Firebase Hosting frontend
- FastAPI backend on Google Cloud Run
- Gemini on Vertex AI through Google ADK
- Firestore for runs, alerts, reports, approvals, and trace events
- Elastic Agent Builder MCP for wildfire evidence retrieval

### 8. Why Elastic MCP

**Title:** Why Elastic MCP matters

- Searches curated wildfire knowledge
- Retrieves SOPs, warning guidance, historical incidents, templates, and reliability notes
- Gives the agent evidence it can preserve in reports
- Falls back deterministically for stable demo behavior

### 9. Demo Flow

**Title:** Demo path

1. Focus live Australian hotspot AOI
2. Ask: "Analyze this region and generate today's report."
3. Review agent trace, risk score, and report
4. Ask a wind/humidity what-if scenario
5. Draft public advisory for human approval

### 10. Closing

**Title:** From scattered signals to explainable action

**Tagline:** Faster situational awareness. Clearer risk reasoning. Human-approved decisions.

## Sources

- Project README: `README.md`
- Royal Commission into National Natural Disaster Arrangements report page: https://www.royalcommission.gov.au/natural-disasters/report
- CAL FIRE 2024 incident archive: https://www.fire.ca.gov/incidents/2024
- EPA Climate Change Indicators: Wildfires: https://www.epa.gov/climate-indicators/climate-change-indicators-wildfires
