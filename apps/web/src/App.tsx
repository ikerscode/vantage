import { useEffect } from "react";

import { useDevAuthBootstrap } from "./api/auth";
import { AOIPanel } from "./components/AOIPanel";
import { CommandBar } from "./components/CommandBar";
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
import { useAuthStore } from "./store/authStore";
import { ensureEventStreamConnected } from "./store/eventStreamStore";
import { useMapStore } from "./store/mapStore";

export function App() {
  useDevAuthBootstrap();
  const mode = useMapStore((s) => s.mode);
  const token = useAuthStore((s) => s.token);

  useEffect(() => {
    ensureEventStreamConnected(token);
  }, [token]);

  useAlertToastWatcher();

  return (
    <div className="hud-shell">
      <MapCanvas />
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
          {mode === "monitor" ? <MonitorPanel /> : <Inspector />}
          <ResultsFeed />
        </div>

        <TemporalScrubber />
        <ToastStack />
      </div>
    </div>
  );
}
