import { Download } from "lucide-react";

import { Button } from "../ui/button";

export function DownloadArtifactButton({label, onClick}: {label: string; onClick: () => void}) {
  return (
    <Button
      aria-label={label}
      size="icon"
      title={label}
      type="button"
      variant="outline"
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        onClick();
      }}
    >
      <Download className="h-4 w-4" />
    </Button>
  );
}
