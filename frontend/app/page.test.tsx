import {render, screen} from "@testing-library/react";
import {beforeEach, describe, expect, it, vi} from "vitest";

// The dashboard must render without waiting on the backend. Every network call is
// left pending here to reproduce a Cloud Run cold start, where /api/hotspots/overview
// takes ~12s to answer.
const pending = <T,>() => new Promise<T>(() => {});

vi.mock("../lib/api", () => ({
  getHotspotOverview: vi.fn(pending),
  getRecentAgentEvents: vi.fn(pending),
  getAgentEventsWebSocketUrl: vi.fn(pending),
  getHotspotFocus: vi.fn(pending),
  getActions: vi.fn(pending),
  getAlerts: vi.fn(pending),
  getMonitorTasks: vi.fn(pending)
}));

// Leaflet needs a real browser canvas; the map is not what this test is about.
vi.mock("../components/MapDashboard", () => ({
  MapDashboard: () => <div data-testid="map-dashboard" />
}));

beforeEach(() => {
  vi.stubGlobal(
    "WebSocket",
    class {
      close() {}
    }
  );
});

describe("dashboard first paint", () => {
  it("renders the operations shell while the hotspot overview is still pending", async () => {
    const {default: Home} = await import("./page");
    render(<Home />);

    // The AOI toolbar heading and the map are the two anchors of the operations shell.
    expect(screen.getByRole("heading", {name: "Australia hotspot overview"})).toBeInTheDocument();
    expect(screen.getByTestId("map-dashboard")).toBeInTheDocument();
  });

  it("does not replace the whole page with a blocking loading screen", async () => {
    const {default: Home} = await import("./page");
    render(<Home />);

    expect(screen.queryByText("Preparing the operations console")).not.toBeInTheDocument();
  });
});
