import { AccountSecuritySettings } from "@/components/account-security-settings";
import { ItemCatalogSettings } from "@/components/item-catalog-settings";
import { CalendarSettingsCard } from "@/components/calendar-settings";
import * as React from "react";
import { Link } from "@tanstack/react-router";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function SettingsPage(): React.JSX.Element {
  return (
    <div className="mx-auto max-w-3xl space-y-4" dir="rtl">
      <h1 className="text-xl font-bold">تنظیمات</h1>
      <nav aria-label="بخش‌های تنظیمات" className="flex flex-wrap gap-3 text-sm">
        <a href="#calendar-settings" className="text-primary">
          تاریخ و تقویم
        </a>
        <a href="#pricing-constants" className="text-primary">
          قیمت‌گذاری
        </a>
        <a href="#item-catalog-settings" className="text-primary">
          اطلاعات پایهٔ کالا
        </a>
        <a href="#account-security" className="text-primary">
          امنیت و ورود
        </a>
        <Link to="/system" className="text-muted-foreground hover:text-foreground">
          سیستم و عملیات
        </Link>
      </nav>
      <CalendarSettingsCard />
      <AccountSecuritySettings />
      <ItemCatalogSettings />
      <Card id="pricing-constants">
        <CardHeader>
          <CardTitle>قیمت‌گذاری</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            همهٔ ثابت‌های ماشین‌حساب قیمت — هفت ثابت اصلی و ثابت‌هایی که خودتان اضافه می‌کنید — در
            یک صفحه جمع شده‌اند.
          </p>
          <Link
            to="/pricing-settings"
            className="inline-flex h-9 items-center rounded-md border px-4 text-sm text-primary hover:bg-accent"
            data-testid="open-pricing-settings"
          >
            رفتن به تنظیمات قیمت‌گذاری
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
