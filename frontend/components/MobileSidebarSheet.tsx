"use client";

import { ReactNode, useEffect, useState } from "react";
import { Menu } from "lucide-react";

import { buttonVariants } from "./ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "./ui/sheet";

export function MobileSidebarSheet({children}: {children: ReactNode}) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return <div className="h-9 w-9 lg:hidden" />;
  }

  return (
    <Sheet>
      <SheetTrigger className={buttonVariants({className: "lg:hidden", size: "icon", variant: "outline"})}>
        <Menu className="h-4 w-4" />
        <span className="sr-only">Open navigation</span>
      </SheetTrigger>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>Operations</SheetTitle>
        </SheetHeader>
        <div className="mt-5 h-[calc(100vh-6rem)]">{children}</div>
      </SheetContent>
    </Sheet>
  );
}
