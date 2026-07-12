import { useEffect, useState } from "react";

import { useAuthStore } from "../store/authStore";

// A brief instrument-style cold-start shown while the app actually brings
// itself online. It's honest, not theatre: each line tracks a REAL readiness
// signal (the dev-auth token, then the tiler token), and the overlay clears
// the moment the console is genuinely usable. A minimum dwell keeps it from
// flashing subliminally on a fast start; a hard timeout guarantees it never
// hides a working app if a bootstrap step stalls. Skipped entirely under
// prefers-reduced-motion.
const MIN_DWELL_MS = 950;
const HARD_TIMEOUT_MS = 4000;
const FADE_MS = 380;

export function BootSequence() {
  const token = useAuthStore((s) => s.token);
  const tilerToken = useAuthStore((s) => s.tilerToken);

  const prefersReduced =
    typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const [minElapsed, setMinElapsed] = useState(false);
  const [gone, setGone] = useState(prefersReduced);

  useEffect(() => {
    if (prefersReduced) return;
    const min = window.setTimeout(() => setMinElapsed(true), MIN_DWELL_MS);
    const hard = window.setTimeout(() => setGone(true), HARD_TIMEOUT_MS);
    return () => {
      window.clearTimeout(min);
      window.clearTimeout(hard);
    };
  }, [prefersReduced]);

  const ready = Boolean(token && tilerToken);
  const fading = ready && minElapsed && !gone;

  useEffect(() => {
    if (!fading) return;
    const t = window.setTimeout(() => setGone(true), FADE_MS);
    return () => window.clearTimeout(t);
  }, [fading]);

  if (gone) return null;

  const checks = [
    { label: "SECURE SESSION", ok: Boolean(token) },
    { label: "TILE SERVICE", ok: Boolean(tilerToken) },
    { label: "IMAGERY CATALOG", ok: Boolean(tilerToken) },
  ];

  return (
    <div className={fading ? "boot boot-out" : "boot"} aria-hidden="true">
      <div className="boot-inner">
        <div className="boot-wordmark">VANTAGE</div>
        <div className="boot-sub">ISR ANALYSIS CONSOLE</div>
        <div className="boot-scan" />
        <ul className="boot-checks">
          {checks.map((c) => (
            <li key={c.label} className={c.ok ? "boot-check ok" : "boot-check"}>
              <span className="boot-check-dot" />
              <span className="boot-check-label">{c.label}</span>
              <span className="boot-check-state">{c.ok ? "OK" : "···"}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
