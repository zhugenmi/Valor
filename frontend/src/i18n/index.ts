import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "@/i18n/locales/en.json";
import zhCN from "@/i18n/locales/zh_CN.json";
import { DEFAULT_LANGUAGE, useSettingsStore } from "@/store/settings-store";

const resources = Object.fromEntries(
  [
    ["en", en],
    ["zh_CN", zhCN],
  ].map(([locale, translation]) => [locale, { translation }]),
);

i18n.use(initReactI18next).init({
  resources,
  lng: useSettingsStore.getState().language,
  fallbackLng: DEFAULT_LANGUAGE,
  debug: import.meta.env.DEV,
  interpolation: {
    escapeValue: false,
  },
  saveMissing: true,
  missingKeyHandler: (_lngs, _ns, key) => {
    if (import.meta.env.DEV) {
      console.log("🚀 ~ missing key:", key);
    }
  },
});

export default i18n;
