import { useEffect } from "react";

import { useDevAuthBootstrap } from "./api/auth";
import { AOIPanel } from "./components/AOIPanel";
import { BootSequence } from "./components/BootSequence";
import { CommandBar } from "./components/CommandBar";
import { Compass } from "./components/Compass";
import { GlobalActivityBar } from "./components/GlobalActivityBar";
import { Inspector } from "./components/Inspector";
import { LayersControl } from "./components/LayersControl";
import { MapCanvas } from "./components/MapCanvas";
import { ModeSwitcher } from "./components/ModeSwitcher";
import { MonitorPanel } from "./components/MonitorPanel";
import { ResultsFeed } from "./components/ResultsFeed";
import { StatusStrip } from "./components/StatusStrip";
import { TemporalScrubber } from "./components/TemporalScrubber";
import { ToastStack } from "./components/Toast";
import { useAlertToastWatcher } from "./lib/useAlertToastWatcher";
import { useAnalysisStore } from "./store/analysisStore";
import { useAuthStore } from "./store/authStore";
import { ensureEventStreamConnected } from "./store/eventStreamStore";
import { useMapStore } from "./store/mapStore";

export function App() {
  useDevAuthBootstrap();
  const mode = useMapStore((s) => s.mode);
  const token = useAuthStore((s) => s.token);
  const inspectorTarget = useAnalysisStore((s) => s.inspectorTarget);

  useEffect(() => {
    ensureEventStreamConnected(token);
  }, [token]);

  useAlertToastWatcher();

  return (
    <div className="hud-shell">
      <MapCanvas />
      <div className="viewport-frame" aria-hidden="true" />
      <BootSequence />
      <GlobalActivityBar />
      <div className="hud-overlay">
        <div className="hud-statusstrip">
          <StatusStrip />
        </div>
        <ModeSwitcher />
        <CommandBar />

        <div className="hud-left">
          <AOIPanel />
          <LayersControl />
        </div>

        <div className="hud-right">
          {/* BRIEF v2, found for real: in Monitor mode this slot always
              rendered MonitorPanel, so clicking an event in the Live Events
              feed below (which only sets inspectorTarget) had nothing to
              show it -- looked like clicking did nothing at all. Once a
              target is selected, show the Inspector (its own × clears
              inspectorTarget, which switches back to MonitorPanel). */}
          {mode === "monitor" && !inspectorTarget ? <MonitorPanel /> : <Inspector />}
          <ResultsFeed />
        </div>

        <Compass />
        <TemporalScrubber />
        <ToastStack />
      </div>
    </div>
  );
}
