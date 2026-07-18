import type { StateStorage } from "zustand/middleware";

/**
 * Browser localStorage-based storage for Zustand persist middleware.
 * Replaces the Tauri plugin-store version that required @tauri-apps/plugin-store.
 */
export class BrowserStoreState implements StateStorage {
  constructor(public storeName: string) {}

  getItem(name: string): string | null {
    try {
      return localStorage.getItem(name);
    } catch {
      return null;
    }
  }

  setItem(name: string, value: string): void {
    try {
      localStorage.setItem(name, value);
    } catch {
      // quota exceeded or private browsing — fail silently
    }
  }

  removeItem(name: string): void {
    try {
      localStorage.removeItem(name);
    } catch {
      // fail silently
    }
  }
}
