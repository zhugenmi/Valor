import { useSystemStore } from "@/store/system-store";
import { apiClient } from "./api-client";

export interface TrackingEvents {
  login: { user_id: string };
  logout: { user_id: string };
  use: { agent_name: string };
}
declare module "react" {
  interface HTMLAttributes<T> extends DOMAttributes<T> {
    "data-track"?: keyof TrackingEvents;
    "data-track-params"?: string;
  }
}

interface TrackerConfig {
  endpoint: string;
}

class Tracker {
  private config: TrackerConfig;

  constructor(config: TrackerConfig) {
    this.config = config;
  }

  public send<K extends keyof TrackingEvents>(
    event: K,
    params?: TrackingEvents[K],
  ) {
    const payload = {
      event,
      user_id: useSystemStore.getState().id,
      ...params,
    };

    apiClient
      .post(this.config.endpoint, payload, {
        keepalive: true,
        wrapError: false,
      })
      .catch(() => {
        /* silently fail */
      });

    if (import.meta.env.DEV) {
      console.log(
        `%c[Tracker] ${event}`,
        "color: #20b2aa; font-weight: bold",
        payload,
      );
    }
  }
}

const tracker = new Tracker({
  endpoint: "/analytics/event",
});

export const withTrack = <T extends keyof TrackingEvents>(
  event: T,
  params?: TrackingEvents[T],
) => {
  return {
    "data-track": event,
    "data-track-params": JSON.stringify(params ?? {}),
  };
};

export { tracker, type TrackerConfig };
