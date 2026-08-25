export type ApiHotspot = {
  lat: number;
  lon: number;
  state?: string | null;
  confidence: string;
  detected_at: string;
  power?: number | null;
  satellite?: string | null;
  sensor?: string | null;
};

export type ApiAoi = {
  bbox?: number[] | null;
  center?: [number, number] | number[];
  radius_km: number;
};

export type ApiHotspotStateSummary = {
  state: string;
  label: string;
  count_24h: number;
  center: [number, number] | number[];
  region_id: string;
  region_name: string;
  radius_options_km: number[];
};

export type ApiHotspotOverview = {
  status: string;
  mode: string;
  source: string;
  cached?: boolean;
  cache_ttl_seconds?: number;
  data: {
    time_window: string;
    updated_at: string;
    total_count_24h: number;
    display_hotspot_count?: number;
    hotspots: ApiHotspot[];
    states: ApiHotspotStateSummary[];
  };
  message?: string;
};

export type ApiHotspotFocus = {
  status: string;
  mode: string;
  source: string;
  cached?: boolean;
  cache_ttl_seconds?: number;
  data: {
    state: string;
    label: string;
    region_id: string;
    region_name: string;
    center: [number, number] | number[];
    radius_km: number;
    hotspot_count_24h: number;
    statewide_hotspot_count_24h: number;
    display_hotspot_count?: number;
    hotspots: ApiHotspot[];
  };
  message?: string;
};

export type ApiOfficialWarningIncident = {
  title: string;
  category: string;
  alert_level: string;
  status: string;
  location: string;
  distance_km: number;
  lat?: number;
  lon?: number;
  updated_at: string | null;
  guid?: string | null;
};

export type ApiHotspotVisualization = {
  status: string;
  mode: string;
  region: {
    region_id: string;
    region_name: string;
    center: [number, number] | number[];
    radius_km: number;
  };
  source: string;
  generated_at: string;
  hotspot_count: number;
  heatmap: {
    cells: {
      lat: number;
      lon: number;
      density: number;
      max_power: number;
      latest_detection: string;
      normalized_intensity: number;
    }[];
    intensity_field: string;
  };
  contours: {
    type: "FeatureCollection";
    features: {
      type: "Feature";
      properties: {
        band: string;
        threshold: number;
        color: string;
        radius_km: number;
      };
      geometry: {
        type: "Polygon";
        coordinates: number[][][];
      };
    }[];
  };
  preview?: {
    format: string;
    encoding: string;
    data_url: string;
    width: number;
    height: number;
    alt: string;
  };
  interpretation: {
    summary: string;
    cluster_center: [number, number] | number[];
    priority: string;
    recommendation: string;
    caveat: string;
  };
  downloads: {
    txt_filename?: string;
    txt_content?: string;
    png_filename?: string;
    json_filename?: string;
    csv_filename?: string;
  };
};

export type ApiRiskTrend = {
  points: {
    run_id?: string;
    risk_score: number;
    risk_level: string;
    date: string;
    type: "historical" | "current" | "forecast";
  }[];
  note: string;
  region_name: string;
  preview?: {
    format: string;
    encoding: string;
    data_url: string;
    alt: string;
  };
  downloads?: {
    png_filename?: string;
  };
  prediction?: Record<string, any>;
};
