import { AlertTriangle, Clock, MapPin } from "lucide-react";

import { Badge } from "./ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";

const alerts = [
  {
    severity: "HIGH",
    region: "Blue Mountains",
    reason: "Risk score increased with elevated wind, low humidity, and hotspot activity.",
    action: "Review advisory and field team brief drafts.",
    created: "10:06"
  },
  {
    severity: "REVIEW",
    region: "Great Western Highway",
    reason: "Exposed road corridor intersects current inspection priority area.",
    action: "Confirm road patrol availability.",
    created: "10:04"
  }
];

export function AlertInbox() {
  return (
    <div className="grid gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Alert Inbox</h2>
        <Badge variant="severe">1 active</Badge>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {alerts.map((alert) => (
          <Card key={`${alert.region}-${alert.created}`}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between gap-2">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <AlertTriangle className="h-4 w-4 text-orange-600" />
                  {alert.region}
                </CardTitle>
                <Badge variant={alert.severity === "HIGH" ? "severe" : "elevated"}>{alert.severity}</Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <p className="text-muted-foreground">{alert.reason}</p>
              <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5" />
                  {alert.created}
                </span>
                <span className="flex items-center gap-1">
                  <MapPin className="h-3.5 w-3.5" />
                  Active
                </span>
              </div>
              <div className="rounded-md bg-muted p-2 text-xs">{alert.action}</div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
