import { Check, ShieldAlert, X } from "lucide-react";

import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent } from "./ui/card";

export function HumanApprovalPanel() {
  return (
    <div className="grid gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Human Approval</h2>
        <Badge variant="elevated">Pending</Badge>
      </div>
      <Card>
        <CardContent className="grid gap-4 p-4 md:grid-cols-[1fr_auto] md:items-center">
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-medium">
              <ShieldAlert className="h-4 w-4 text-orange-600" />
              Public advisory draft
            </div>
            <p className="text-sm text-muted-foreground">
              External publication is blocked until a human approver accepts the action.
            </p>
          </div>
          <div className="flex gap-2">
            <Button size="sm" type="button">
              <Check className="mr-2 h-4 w-4" />
              Approve
            </Button>
            <Button size="sm" variant="outline" type="button">
              <X className="mr-2 h-4 w-4" />
              Reject
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
