/**
 * Where the API/tiler live is only known at deploy time, not build time:
 * the desktop launcher picks localhost ports dynamically to dodge
 * conflicts, and a docker-compose deployment may remap ports too. So the
 * built SPA never bakes these in via import.meta.env. Two mechanisms,
 * checked in order, both handled before React renders (see main.tsx):
 *
 *  1. window.__VANTAGE_RUNTIME_CONFIG__ — the desktop launcher injects this
 *     via a Tauri initialization_script that runs before the page's own JS
 *     (see apps/launcher/launcher-core/src/config.rs), since writing into
 *     the bundled webview assets at runtime is fragile across bundle
 *     formats and breaks macOS code-signing.
 *  2. GET /runtime-config.json — the plain docker-compose path (served
 *     from apps/web/public/ verbatim in dev; nothing rewrites it there).
 */
export interface RuntimeConfig {
  apiBaseUrl: string;
  tilerBaseUrl: string;
  appVersion: string | null;
  /** BRIEF v1.8: see apps/api/app/routers/auth.py's _has_valid_dev_token_secret
   * doc comment — a portable alternative to the loopback-only network check
   * for /api/auth/dev-token, needed because that check doesn't generalize to
   * every container runtime (found for real: fails under Podman). Empty for
   * the plain docker-compose path, where the network check already works. */
  devTokenSecret: string;
}

declare global {
  interface Window {
    __VANTAGE_RUNTIME_CONFIG__?: Partial<RuntimeConfig>;
  }
}

const FALLBACK: RuntimeConfig = {
  apiBaseUrl: "http://localhost:8000",
  tilerBaseUrl: "http://localhost:8001",
  appVersion: null,
  devTokenSecret: "",
};

let cached: RuntimeConfig | null = null;

export async function loadRuntimeConfig(): Promise<RuntimeConfig> {
  if (cached) return cached;

  if (window.__VANTAGE_RUNTIME_CONFIG__) {
    const injected = window.__VANTAGE_RUNTIME_CONFIG__;
    cached = {
      apiBaseUrl: injected.apiBaseUrl ?? FALLBACK.apiBaseUrl,
      tilerBaseUrl: injected.tilerBaseUrl ?? FALLBACK.tilerBaseUrl,
      appVersion: injected.appVersion ?? null,
      devTokenSecret: injected.devTokenSecret ?? FALLBACK.devTokenSecret,
    };
    return cached;
  }

  try {
    const response = await fetch("/runtime-config.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`status ${response.status}`);
    const data = (await response.json()) as Partial<RuntimeConfig>;
    cached = {
      apiBaseUrl: data.apiBaseUrl ?? FALLBACK.apiBaseUrl,
      tilerBaseUrl: data.tilerBaseUrl ?? FALLBACK.tilerBaseUrl,
      appVersion: data.appVersion ?? null,
      devTokenSecret: data.devTokenSecret ?? FALLBACK.devTokenSecret,
    };
  } catch {
    // Missing/unreachable runtime-config.json shouldn't hard-fail the app —
    // fall back to the same localhost defaults docker-compose exposes.
    cached = FALLBACK;
  }
  return cached;
}

/** Only valid after loadRuntimeConfig() has resolved once (see main.tsx). */
export function getRuntimeConfig(): RuntimeConfig {
  if (!cached) throw new Error("runtime config accessed before loadRuntimeConfig() resolved");
  return cached;
}
