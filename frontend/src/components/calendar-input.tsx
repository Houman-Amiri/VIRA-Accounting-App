/** A real Jalali/Gregorian text input; parent state always contains ISO date-only. */
import { useEffect, useRef, useState } from "react";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { inputToIso, isoToInput, tehranToday } from "@/lib/calendar";
import { useCalendar } from "@/lib/calendar-settings";

export function CalendarInput({
  value,
  onChange,
  id,
  label,
  required = false,
  onInvalidChange,
}: {
  value: string;
  onChange: (iso: string) => void;
  id: string;
  label: string;
  required?: boolean;
  onInvalidChange?: (invalid: boolean) => void;
}) {
  const { calendar, ready, error } = useCalendar();
  const [draft, setDraft] = useState(() => isoToInput(value, calendar));
  const last = useRef({ value, calendar });
  useEffect(() => {
    if (value !== last.current.value || calendar !== last.current.calendar) {
      setDraft(isoToInput(value, calendar));
      onInvalidChange?.(false);
    }
    last.current = { value, calendar };
  }, [value, calendar, onInvalidChange]);
  const invalid =
    (!!draft.trim() && !inputToIso(draft, calendar)) || (!!value && !isoToInput(value, calendar));
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>
        {label} ({calendar === "jalali" ? "شمسی" : "میلادی"})
      </Label>
      <Input
        id={id}
        data-testid={id}
        dir="ltr"
        className="num"
        required={required}
        disabled={!ready}
        value={draft}
        placeholder={calendar === "jalali" ? "1405/07/25" : "2026/10/17"}
        aria-invalid={invalid}
        aria-describedby={`${id}-hint`}
        onChange={(e) => {
          const raw = e.target.value;
          setDraft(raw);
          const iso = inputToIso(raw, calendar) ?? "";
          last.current = { value: iso, calendar };
          onInvalidChange?.(!!raw.trim() && !iso);
          onChange(iso);
        }}
      />
      <p
        id={`${id}-hint`}
        className={invalid || error ? "text-xs text-destructive" : "text-xs text-muted-foreground"}
        role={invalid || error ? "alert" : undefined}
      >
        {error ??
          (!ready
            ? "دریافت تنظیم تقویم…"
            : invalid
              ? "تاریخ نامعتبر است؛ سال/ماه/روز را در تقویم انتخاب‌شده وارد کنید."
              : "سال/ماه/روز؛ ارقام فارسی یا لاتین — زمان تهران")}
      </p>
      {required && (
        <button
          className="text-xs text-primary underline"
          type="button"
          disabled={!ready}
          onClick={() => {
            const today = tehranToday();
            last.current = { value: today, calendar };
            setDraft(isoToInput(today, calendar));
            onChange(today);
          }}
        >
          امروز تهران
        </button>
      )}
    </div>
  );
}
