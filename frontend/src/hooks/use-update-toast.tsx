import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

export function useUpdateToast() {
  const { t } = useTranslation();

  const checkForUpdatesSilent = useCallback(async () => {
    // In web mode, auto-update is handled by the browser.
    // This hook is kept as a no-op to avoid breaking callers.
  }, []);

  const checkAndUpdate = useCallback(async () => {
    toast.info(t("updates.toast.latest"));
  }, [t]);

  return { checkAndUpdate, checkForUpdatesSilent };
}
