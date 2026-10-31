/**
 * راهنمای گام‌به‌گام — the in-app walkthrough (item 9 of the owner's list).
 *
 * Every page that used to need a manual (bank statement, receipts, new entry)
 * carries its own short numbered guide. It is collapsible and remembers being
 * dismissed per page, so it helps a first-time user without nagging a daily one.
 */
import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ChevronDown, ChevronUp, ListChecks } from "lucide-react";

export interface GuideStep {
  title: string;
  body: string;
}

const STORAGE_PREFIX = "vira-guide-dismissed:";

function readDismissed(id: string): boolean {
  try {
    return window.localStorage.getItem(STORAGE_PREFIX + id) === "1";
  } catch {
    return false;
  }
}

function writeDismissed(id: string, value: boolean): void {
  try {
    if (value) window.localStorage.setItem(STORAGE_PREFIX + id, "1");
    else window.localStorage.removeItem(STORAGE_PREFIX + id);
  } catch {
    /* private mode / disabled storage: the guide simply stays expanded */
  }
}

export function StepGuide({
  id,
  title,
  steps,
  intro,
}: {
  id: string;
  title: string;
  steps: GuideStep[];
  intro?: string;
}): React.JSX.Element {
  const [dismissed, setDismissed] = React.useState(() => readDismissed(id));
  const [open, setOpen] = React.useState(true);

  const dismiss = (): void => {
    writeDismissed(id, true);
    setDismissed(true);
  };
  const restore = (): void => {
    writeDismissed(id, false);
    setDismissed(false);
    setOpen(true);
  };

  if (dismissed) {
    return (
      <Button
        variant="ghost"
        size="sm"
        className="w-fit"
        data-testid={`guide-${id}-reopen`}
        onClick={restore}
      >
        <ListChecks /> نمایش راهنمای گام‌به‌گام
      </Button>
    );
  }

  return (
    <Card data-testid={`guide-${id}`} className="border-primary/30 bg-primary/5">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <ListChecks className="h-4 w-4" aria-hidden />
          {title}
        </CardTitle>
        <div className="flex gap-1">
          <Button
            variant="ghost"
            size="sm"
            aria-expanded={open}
            data-testid={`guide-${id}-toggle`}
            onClick={() => setOpen((value) => !value)}
          >
            {open ? <ChevronUp /> : <ChevronDown />}
            {open ? "بستن فهرست" : "نمایش گام‌ها"}
          </Button>
          <Button variant="ghost" size="sm" data-testid={`guide-${id}-dismiss`} onClick={dismiss}>
            دیگر نشان نده
          </Button>
        </div>
      </CardHeader>
      {open && (
        <CardContent className="space-y-2">
          {intro && <p className="text-sm text-muted-foreground">{intro}</p>}
          <ol className="space-y-2" data-testid={`guide-${id}-steps`}>
            {steps.map((step, index) => (
              <li key={step.title} className="flex gap-2 text-sm">
                <span
                  className="num mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground"
                  aria-hidden
                >
                  {index + 1}
                </span>
                <span>
                  <span className="font-medium">{step.title}</span>
                  <span className="block text-muted-foreground">{step.body}</span>
                </span>
              </li>
            ))}
          </ol>
        </CardContent>
      )}
    </Card>
  );
}
