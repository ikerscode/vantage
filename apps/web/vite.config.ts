import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

// Belt-and-suspenders no-phone-home guarantee: the app only ever needs to
// reach itself and the locally-bound API/tiler services (whatever port the
// launcher assigns them — see lib/runtimeConfig.ts), never a third-party
// host. This makes any dormant CDN-fallback code path in a transitive
// dependency (WebGL debug tooling, loaders.gl worker fallback — see
// PACKAGE_REPORT.md) provably inert, not just unreached-in-practice.
// Production-only: a strict script-src would break Vite's dev-time HMR.
function airGapCsp(): Plugin {
  const csp = [
    "default-src 'self'",
    "connect-src 'self' http://localhost:* http://127.0.0.1:*",
    "img-src 'self' data: blob: http://localhost:* http://127.0.0.1:*",
    "style-src 'self' 'unsafe-inline'",
    "script-src 'self'",
    "worker-src 'self' blob:",
    "font-src 'self'",
    // SEC-05: this app is never meant to be framed by anything, and has no
    // <base> or <object>/<embed> use anywhere — closing all three off
    // removes a whole class of clickjacking/base-tag-injection attacks for
    // free, with zero functional cost.
    "frame-ancestors 'none'",
    "base-uri 'none'",
    "object-src 'none'",
  ].join("; ");
  return {
    name: "vantage-airgap-csp",
    apply: "build",
    transformIndexHtml(html) {
      return html.replace(
        "</head>",
        `    <meta http-equiv="Content-Security-Policy" content="${csp}" />\n  </head>`,
      );
    },
  };
}

export default defineConfig({
  plugins: [react(), airGapCsp()],
  server: {
    port: 5173,
  },
  build: {
    // The map-vendor chunk below (maplibre-gl + deck.gl) is irreducibly
    // ~2.4MB minified -- that's the real, accounted-for size of this
    // locked stack (see CLAUDE.md), not a splitting failure, so the
    // default 500kB warning threshold is the wrong bar for it.
    chunkSizeWarningLimit: 2600,
    rollupOptions: {
      output: {
        // The map/rendering stack (maplibre-gl + the deck.gl family) is
        // legitimately large and changes far less often than app code —
        // splitting it into its own chunk doesn't shrink the total download,
        // but it means an app-code-only release doesn't invalidate the
        // browser's cache of this chunk, and first paint isn't blocked on
        // parsing app code bundled inline with it.
        manualChunks: {
          "map-vendor": ["maplibre-gl", "deck.gl", "@deck.gl/mapbox", "@deck.gl-community/editable-layers"],
        },
      },
    },
  },
});
