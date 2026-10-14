/**
 * Persian-only i18n (Phase 7 §3) — react-i18next with namespace-split JSON
 * files under /locales/fa/{common,ledger,reports,validation}.json.
 *
 * Strictly fa-IR: NO English resources, NO language switcher, NO numeral
 * toggle.  Persian numerals are applied at the presentation layer only
 * (see lib/fa.ts) — internal values stay machine-readable.
 */
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import common from "@/locales/fa/common.json";
import ledger from "@/locales/fa/ledger.json";
import reports from "@/locales/fa/reports.json";
import validation from "@/locales/fa/validation.json";

export const NAMESPACES = ["common", "ledger", "reports", "validation"] as const;
export type Namespace = (typeof NAMESPACES)[number];

if (!i18n.isInitialized) {
  void i18n.use(initReactI18next).init({
    lng: "fa",
    fallbackLng: "fa",
    supportedLngs: ["fa"],
    defaultNS: "common",
    ns: NAMESPACES as unknown as string[],
    resources: {
      fa: { common, ledger, reports, validation },
    },
    interpolation: { escapeValue: false },
    returnEmptyString: false,
  });
}

export default i18n;
