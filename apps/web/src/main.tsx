import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-sans/700.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";

import { App } from "./App";
import { loadRuntimeConfig } from "./lib/runtimeConfig";
import "./styles.css";
import { pushErrorToast } from "./store/toastStore";

function describeError(error: unknown): string {
  return error instanceof Error ? error.message : "request failed";
}

// BRIEF v2, found for real: no mutation anywhere in this app surfaced its
// own failures — "RUN ANALYSIS" (and every other action button) looked
// completely broken when its request failed, because nothing ever told
// the user it had. Routing every query/mutation failure through one place
// means a new feature can't reintroduce a silent failure by omission —
// only genuinely expected states (e.g. a 404 the UI already handles some
// other way) need an explicit opt-out, via `meta: { silent: true }`.
const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error, query) => {
      if (query.meta?.silent) return;
      pushErrorToast(describeError(error));
    },
  }),
  mutationCache: new MutationCache({
    onError: (error, _variables, _context, mutation) => {
      if (mutation.meta?.silent) return;
      pushErrorToast(describeError(error));
    },
  }),
});

// Resolve where the API/tiler actually live before anything renders — see
// lib/runtimeConfig.ts for why this can't be a build-time constant.
loadRuntimeConfig().then(() => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </StrictMode>,
  );
});
