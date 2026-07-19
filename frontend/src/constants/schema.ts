import type { TFunction } from "i18next";
import { z } from "zod";

export const createAiModelSchema = (t: TFunction) =>
  z.object({
    provider: z.string().min(1, t("validation.aiModel.providerRequired")),
    model_id: z.string().min(1, t("validation.aiModel.modelIdRequired")),
    api_key: z.string().min(1, t("validation.aiModel.apiKeyRequired")),
  });
