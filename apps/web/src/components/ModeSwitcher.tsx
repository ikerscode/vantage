import { type Mode, useMapStore } from "../store/mapStore";

const MODES: Mode[] = ["explore", "analyze", "monitor"];

export function ModeSwitcher() {
  const mode = useMapStore((s) => s.mode);
  const setMode = useMapStore((s) => s.setMode);

  return (
    <div className="panel mode-switcher">
      {MODES.map((m) => (
        <button
          key={m}
          className={m === mode ? "mode-switcher-segment active" : "mode-switcher-segment"}
          onClick={() => setMode(m)}
        >
          {m}
        </button>
      ))}
    </div>
  );
}
