/**
 * Command palette — cmdk + react-hotkeys-hook (Cmd/Ctrl+K).
 * Navigation + actions in Persian, RTL dialog.
 */
import * as React from "react";
import { useNavigate } from "@tanstack/react-router";
import { Command } from "cmdk";
import { useHotkeys } from "react-hotkeys-hook";
import { useUiStore } from "@/store/ui";
import {
  BookOpenText,
  Building2,
  FileText,
  LayoutDashboard,
  Moon,
  Receipt,
  Scale,
  Sun,
  Tag,
  Upload,
  Wallet,
} from "lucide-react";

interface CommandItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  action: () => void;
  keywords: string;
}

export function CommandPalette(): React.JSX.Element {
  const navigate = useNavigate();
  const { commandPaletteOpen, setCommandPaletteOpen, toggleTheme, theme } = useUiStore();

  useHotkeys("mod+k", (e) => {
    e.preventDefault();
    setCommandPaletteOpen(!commandPaletteOpen);
  }, { enableOnFormTags: true });

  useHotkeys("esc", () => setCommandPaletteOpen(false), { enabled: commandPaletteOpen });

  const items: CommandItem[] = [
    { id: "dashboard", label: "داشبورد", icon: <LayoutDashboard />, keywords: "dashboard خانه", action: () => navigate({ to: "/" }) },
    { id: "journal-new", label: "سند جدید", icon: <FileText />, keywords: "journal سند حسابداری", action: () => navigate({ to: "/journal/new" }) },
    { id: "journal", label: "دفتر اسناد", icon: <BookOpenText />, keywords: "journal list اسناد", action: () => navigate({ to: "/journal" }) },
    { id: "accounts", label: "چارت حساب‌ها", icon: <Building2 />, keywords: "accounts chart", action: () => navigate({ to: "/accounts" }) },
    { id: "bank-import", label: "ورود صورت‌حساب بانکی", icon: <Upload />, keywords: "bank import csv", action: () => navigate({ to: "/bank-import" }) },
    { id: "reconcile", label: "تطبیق بانکی", icon: <Scale />, keywords: "reconcile تطبیق", action: () => navigate({ to: "/reconcile" }) },
    { id: "statements", label: "صورت‌های مالی", icon: <Wallet />, keywords: "reports صورت", action: () => navigate({ to: "/statements" }) },
    { id: "price-calc", label: "ماشین‌حساب قیمت‌گذاری", icon: <Tag />, keywords: "price قیمت", action: () => navigate({ to: "/price-calc" }) },
    { id: "receipts", label: "اسناد و رسیدها", icon: <Receipt />, keywords: "receipt رسید", action: () => navigate({ to: "/receipts" }) },
    {
      id: "theme",
      label: theme === "light" ? "حالت تاریک" : "حالت روشن",
      icon: theme === "light" ? <Moon /> : <Sun />,
      keywords: "theme تم",
      action: toggleTheme,
    },
  ];

  if (!commandPaletteOpen) return <></>;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-[15vh]"
      onClick={() => setCommandPaletteOpen(false)}
      role="presentation"
    >
      <div
        className="w-full max-w-lg overflow-hidden rounded-xl border bg-card text-card-foreground shadow-2xl"
        dir="rtl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="پالت فرمان‌ها"
      >
        <Command loop label="پالت فرمان‌ها">
          <Command.Input
            placeholder="جستجوی دستورات… (Ctrl+K)"
            className="w-full border-b bg-transparent px-4 py-3 text-sm outline-none placeholder:text-muted-foreground"
          />
          <Command.List className="max-h-80 overflow-y-auto p-2">
            <Command.Empty className="p-6 text-center text-sm text-muted-foreground">موردی یافت نشد.</Command.Empty>
            <Command.Group heading="ناوبری" className="text-xs text-muted-foreground">
              {items.map((item) => (
                <Command.Item
                  key={item.id}
                  value={`${item.label} ${item.keywords}`}
                  onSelect={() => {
                    item.action();
                    setCommandPaletteOpen(false);
                  }}
                  className="flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-sm aria-selected:bg-accent"
                >
                  <span className="text-muted-foreground">{item.icon}</span>
                  {item.label}
                </Command.Item>
              ))}
            </Command.Group>
          </Command.List>
        </Command>
      </div>
    </div>
  );
}
