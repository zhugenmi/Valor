/**
 * Browser environment info — always returns non-Tauri.
 * Replaces the Tauri version that imported @tauri-apps/api/app.
 */
export function useTauriInfo() {
  return { isTauriApp: false, appVersion: null, isLoading: false };
}
