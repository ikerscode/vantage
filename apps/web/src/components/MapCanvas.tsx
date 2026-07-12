import { DrawPolygonMode, EditableGeoJsonLayer, ViewMode } from "@deck.gl-community/editable-layers";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { GeoJsonLayer } from "deck.gl";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";

import { useAnalysis } from "../api/analyses";
import { useAois } from "../api/aois";
import { useDetections } from "../api/detections";
import { darkVoidStyle } from "../lib/maplibreStyle";
import { getRuntimeConfig } from "../lib/runtimeConfig";
import { ndviTilejsonUrl, trueColorTilejsonUrl } from "../lib/tileUrl";
import { useAnalysisStore } from "../store/analysisStore";
import { useAoiStore } from "../store/aoiStore";
import { useAuthStore } from "../store/authStore";
import { useMapStore } from "../store/mapStore";

// Chrome/selection uses one cyan accent. AOIs stay neutral. Detections and
// the change overlay, by explicit request, are the exception: activity the
// operator needs to notice is flagged in an alerting palette — detections
// pulse RED, the change footprint pulses ORANGE — rather than the old neutral
// off-white. (This deliberately departs from the "no red boxes" default for
// the two layers whose entire job is to surface things that changed.)
const ACCENT_LINE: [number, number, number, number] = [63, 184, 212, 255];
const ACCENT_FILL: [number, number, number, number] = [63, 184, 212, 36];
const MUTED_LINE: [number, number, number, number] = [139, 148, 158, 160];
const MUTED_FILL: [number, number, number, number] = [139, 148, 158, 18];
// Detection red (matches the --alert token used across the HUD chrome).
const DETECTION_RED: [number, number, number] = [248, 81, 73];
const DETECTION_SELECTED_LINE: [number, number, number, number] = [255, 138, 128, 255];

// Pulse (not blink): the detection/change overlays breathe smoothly between a
// bright and a dim level. A single requestAnimationFrame loop computes a
// continuous cosine brightness (bright → dim → bright over PULSE_PERIOD_MS) and
// both overlays read the same level, so they pulse in sync. Driving the level
// ourselves (rather than a deck.gl/MapLibre transition) is deliberate: deck.gl
// composite layers don't forward `transitions` to their sublayers, so that
// route would silently degrade to a hard on/off blink. BRIGHT/DIM are fractions
// of each layer's own opacity.
const PULSE_PERIOD_MS = 1800;
const PULSE_BRIGHT = 1;
const PULSE_DIM = 0.38;

const EMPTY_FEATURE_COLLECTION = { type: "FeatureCollection" as const, features: [] };

// ---- Graticule ------------------------------------------------------------
// A quiet lat/lon grid rendered client-side over the whole map. This is the
// map's answer to "the void is featureless": real cartographic structure —
// actual coordinates, the plotting-board vernacular of this domain — instead
// of decoration, and generated locally so it costs nothing and works
// air-gapped (no tiles involved). Neutral grey only (the accent never touches
// map-space content); major lines land on 5× the minor spacing.
const GRATICULE_MINOR: [number, number, number, number] = [139, 148, 158, 20];
const GRATICULE_MAJOR: [number, number, number, number] = [139, 148, 158, 40];
// Spacing ladder chosen so roughly 6–14 lines are on screen at any zoom.
const GRATICULE_STEPS = [0.01, 0.02, 0.05, 0.1, 0.25, 0.5, 1, 2, 5];

function graticuleSpacing(spanDeg: number): number {
  const target = spanDeg / 8;
  return GRATICULE_STEPS.find((s) => s >= target) ?? 10;
}

function buildGraticule(map: maplibregl.Map) {
  const bounds = map.getBounds();
  const west = bounds.getWest();
  const east = bounds.getEast();
  const south = Math.max(bounds.getSouth(), -85);
  const north = Math.min(bounds.getNorth(), 85);
  const spacing = graticuleSpacing(Math.max(east - west, north - south));

  const features: {
    type: "Feature";
    geometry: { type: "LineString"; coordinates: [number, number][] };
    properties: { major: boolean };
  }[] = [];
  // Integer line indices (not `lon += spacing`) so float drift can't skew the
  // grid, and `i % 5` cleanly marks every fifth line as major.
  for (let i = Math.floor(west / spacing); i <= Math.ceil(east / spacing); i++) {
    const lon = i * spacing;
    features.push({
      type: "Feature",
      geometry: { type: "LineString", coordinates: [[lon, south], [lon, north]] },
      properties: { major: i % 5 === 0 },
    });
  }
  for (let i = Math.floor(south / spacing); i <= Math.ceil(north / spacing); i++) {
    const lat = i * spacing;
    if (lat < -85 || lat > 85) continue;
    features.push({
      type: "Feature",
      geometry: { type: "LineString", coordinates: [[west, lat], [east, lat]] },
      properties: { major: i % 5 === 0 },
    });
  }
  return { type: "FeatureCollection" as const, features };
}

// BRIEF v2, found for real on a live install: with no basemap for scale, a
// user zoomed all the way out (Z1, ~world span) and drew a 32-million-km²
// AOI — whose imagery search matched millions of scenes and hung the UI.
// A minimum zoom is the root-cause fix for that whole class of problem: it
// caps how large an area can be framed (and therefore drawn) at once.
//
// Z10 ≈ 119 km view radius (~237 km across) at mid-latitude — chosen to
// match the ~100 km footprint of a single Sentinel-2 granule, which is the
// most imagery a single scene can fill anyway (beyond it, coverage is
// patchy until the multi-scene mosaic exists). It comfortably frames any
// realistic operational AOI while making a continent-scale draw physically
// impossible, and sits well inside the true-color COG's usable range so
// imagery is actually visible wherever you can draw. (An earlier value of
// Z5 was shipped by mistake — it allowed a ~3,800 km radius, continental,
// and did NOT prevent the overload trap it was meant to.)
const MIN_ZOOM = 10;

export function MapCanvas() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  // The tilejson URL each raster source was last built with. A MapLibre raster
  // source's URL can't be mutated in place, so when the active scene/analysis
  // changes (new URL) we must tear the source down and re-add it — otherwise
  // the layer keeps serving the PREVIOUS AOI's imagery. This was the other half
  // of "no imagery until I reload": selecting a new AOI updated the scene but
  // the source kept its old URL, so nothing new ever loaded until a full reload
  // wiped the map and rebuilt the source from scratch.
  const rasterSourceUrls = useRef<Record<string, string>>({});

  const viewState = useMapStore((s) => s.viewState);
  const setViewState = useMapStore((s) => s.setViewState);
  const setCursorLatLon = useMapStore((s) => s.setCursorLatLon);
  const flyToRequest = useMapStore((s) => s.flyToRequest);
  const clearFlyToRequest = useMapStore((s) => s.clearFlyToRequest);

  const { data: aois } = useAois();
  const selectedAoiId = useAoiStore((s) => s.selectedAoiId);
  const setSelectedAoiId = useAoiStore((s) => s.setSelectedAoiId);
  const draftGeometry = useAoiStore((s) => s.draftGeometry);
  const setDraftGeometry = useAoiStore((s) => s.setDraftGeometry);
  const isDrawing = useAoiStore((s) => s.isDrawing);

  const activeRasterLayer = useAnalysisStore((s) => s.activeRasterLayer);
  const rasterOpacity = useAnalysisStore((s) => s.rasterOpacity);
  const changeVisible = useAnalysisStore((s) => s.changeVisible);
  const detectionsVisible = useAnalysisStore((s) => s.detectionsVisible);
  const selectedScene = useAnalysisStore((s) => s.selectedScene);
  const activeAnalysisId = useAnalysisStore((s) => s.activeAnalysisId);
  const inspectorTarget = useAnalysisStore((s) => s.inspectorTarget);
  const setInspectorTarget = useAnalysisStore((s) => s.setInspectorTarget);

  const { data: activeAnalysis } = useAnalysis(activeAnalysisId ?? undefined);
  const { data: detections } = useDetections(activeAnalysisId ?? undefined);
  // Subscribed (not just read at request time like transformRequest does)
  // so the raster effect below re-runs when the token arrives — see its
  // comment for the race this closes.
  const tilerToken = useAuthStore((s) => s.tilerToken);

  // Shared pulse brightness (fraction of full opacity) for the detection/change
  // overlays, driven by one rAF loop so the two breathe in sync. Quantized to
  // ~2% steps so we only re-render when the level meaningfully moves (near the
  // cosine's peaks it barely changes, so this idles most of the cycle).
  // True while MapLibre is fetching raster tiles (pan, zoom, scene switch).
  // Tile fetches don't go through react-query, so the global activity bar
  // can't see them — this drives a small "loading imagery" chip so tiles
  // arriving late still reads as "working", not a stuck/ghost view.
  const [tilesLoading, setTilesLoading] = useState(false);

  const [pulseLevel, setPulseLevel] = useState(PULSE_BRIGHT);
  useEffect(() => {
    const anyOverlay = detectionsVisible || changeVisible;
    // Paused while drawing: the pulse re-runs the vector-layer effect, and
    // there's no reason to churn the editable draw layer mid-draw.
    if (!anyOverlay || isDrawing) {
      setPulseLevel(PULSE_BRIGHT);
      return;
    }
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const phase = ((now - start) % PULSE_PERIOD_MS) / PULSE_PERIOD_MS;
      const s = 0.5 + 0.5 * Math.cos(phase * 2 * Math.PI); // 1 at phase 0 → 0 at 0.5
      const level = PULSE_DIM + (PULSE_BRIGHT - PULSE_DIM) * s;
      setPulseLevel((prev) => (Math.abs(prev - level) >= 0.02 ? level : prev));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [detectionsVisible, changeVisible, isDrawing]);

  // Initialize the map + deck.gl overlay once.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: darkVoidStyle,
      center: [viewState.longitude, viewState.latitude],
      zoom: Math.max(viewState.zoom, MIN_ZOOM),
      minZoom: MIN_ZOOM,
      pitch: viewState.pitch,
      bearing: viewState.bearing,
      attributionControl: false,
      // SEC-01: the tiler requires X-Tiler-Token on every request. Reads
      // the current token from the store at request time (not captured at
      // map-construction time) since it arrives asynchronously, after the
      // dev-auth bootstrap — see api/auth.ts, store/authStore.ts.
      //
      // Scoped by URL prefix, NOT by resourceType (BRIEF v1.8, found for
      // real on a user's install — the first time anyone ever got the
      // packaged UI far enough to fetch a real tile): a raster source added
      // by tilejson URL makes MapLibre fetch the tilejson itself first, and
      // that request is resourceType "Source", not "Tile" — the previous
      // narrowing to "Tile" meant the tilejson fetch NEVER carried the
      // token, 401ing every layer before a single tile was ever requested.
      // The URL-prefix check is what keeps the token from leaking to other
      // hosts (Earth Search etc.); resourceType added nothing but this bug.
      transformRequest: (url) => {
        const { tilerBaseUrl } = getRuntimeConfig();
        if (url.startsWith(tilerBaseUrl)) {
          const tilerToken = useAuthStore.getState().tilerToken;
          if (tilerToken) {
            return { url, headers: { "X-Tiler-Token": tilerToken } };
          }
        }
        return { url };
      },
    });
    mapRef.current = map;

    // interleaved: true is load-bearing, not cosmetic (BRIEF v2, found for
    // real): @deck.gl/mapbox's default "overlaid" mode gives deck.gl its own
    // canvas with pointer-events: none, and feeds MapLibre's click/drag
    // events into it by calling Deck's internal _onEvent method directly --
    // bypassing the shared mjolnir.js event bus entirely. EditableGeoJsonLayer
    // (AOI drawing) registers its own listener ON that same bus to catch raw
    // clicks, so in overlaid mode it never receives a single one -- drawing
    // silently does nothing, no matter what the map's own dragPan/
    // doubleClickZoom state is. Interleaved mode shares MapLibre's real
    // canvas and real event dispatch instead, restoring genuine multi-
    // listener mjolnir.js behavior.
    const overlay = new MapboxOverlay({ interleaved: true, layers: [] });
    map.addControl(overlay as unknown as maplibregl.IControl);
    overlayRef.current = overlay;

    map.on("moveend", () => {
      const center = map.getCenter();
      setViewState({
        longitude: center.lng,
        latitude: center.lat,
        zoom: map.getZoom(),
        pitch: map.getPitch(),
        bearing: map.getBearing(),
      });
    });

    map.on("mousemove", (e) => {
      setCursorLatLon({ lat: e.lngLat.lat, lon: e.lngLat.lng });
    });
    map.on("mouseout", () => setCursorLatLon(null));

    // Tile-load feedback: "loading" the moment a source starts fetching,
    // cleared on "idle" (MapLibre fires it once everything on screen has
    // finished rendering with nothing left pending).
    map.on("sourcedataloading", () => setTilesLoading(true));
    map.on("idle", () => setTilesLoading(false));

    return () => {
      map.remove();
      mapRef.current = null;
      overlayRef.current = null;
    };
    // Deliberately runs once — viewState changes are pushed into the map
    // imperatively elsewhere, not by re-running this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // CommandBar-driven "jump to" requests.
  useEffect(() => {
    if (!flyToRequest || !mapRef.current) return;
    const target = {
      center: [flyToRequest.longitude, flyToRequest.latitude] as [number, number],
      zoom: flyToRequest.zoom ?? mapRef.current.getZoom(),
    };
    // instant → jumpTo (no animation): used for the first auto-navigation so
    // the user isn't staring at empty void during a multi-second globe fly.
    if (flyToRequest.instant) mapRef.current.jumpTo(target);
    else mapRef.current.flyTo({ ...target, essential: true });
    clearFlyToRequest();
  }, [flyToRequest, clearFlyToRequest]);

  // While drawing, only doubleClickZoom is disabled — DrawPolygonMode uses
  // double-click to finish the ring, and MapLibre would otherwise zoom on
  // that same gesture. dragPan deliberately stays ENABLED (BRIEF v2, two
  // rounds of live testing): it was originally disabled too, back when
  // clicks were being eaten before deck.gl saw them — but the real cause of
  // that was overlaid-mode event forwarding, since fixed properly with
  // MapboxOverlay's interleaved mode (see the overlay construction above).
  // With clicks genuinely reaching EditableGeoJsonLayer, a plain click (no
  // movement) adds a vertex without triggering dragPan at all — and keeping
  // dragPan on means you can still pan/zoom mid-draw to reach the far side
  // of a large area, instead of being locked to whatever was on screen when
  // you clicked DRAW (found for real: a user who couldn't navigate mid-draw
  // ended up drawing a continent-sized AOI from a zoomed-out view instead).
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (isDrawing) {
      map.doubleClickZoom.disable();
    } else {
      map.doubleClickZoom.enable();
    }
  }, [isDrawing]);

  // Vector layers: graticule, saved AOIs, the in-progress AOI draw layer,
  // detection boxes.
  useEffect(() => {
    const overlay = overlayRef.current;
    if (!overlay) return;

    // Rebuilt on every moveend (viewState is a dep) — generation is a few
    // dozen two-point lines, far cheaper than one tile fetch.
    const graticuleLayer = new GeoJsonLayer({
      id: "graticule",
      data: mapRef.current ? buildGraticule(mapRef.current) : EMPTY_FEATURE_COLLECTION,
      pickable: false,
      stroked: true,
      filled: false,
      getLineColor: (f: { properties: { major: boolean } }) =>
        f.properties.major ? GRATICULE_MAJOR : GRATICULE_MINOR,
      lineWidthUnits: "pixels",
      getLineWidth: (f: { properties: { major: boolean } }) => (f.properties.major ? 1 : 0.5),
    });

    const savedAoisLayer = new GeoJsonLayer({
      id: "saved-aois",
      data: {
        type: "FeatureCollection",
        features: (aois ?? []).map((aoi) => ({
          type: "Feature" as const,
          geometry: aoi.geometry,
          properties: { id: aoi.id, name: aoi.name },
        })),
      },
      pickable: true,
      stroked: true,
      filled: true,
      getLineColor: (f: { properties: { id: string } }) =>
        f.properties.id === selectedAoiId ? ACCENT_LINE : MUTED_LINE,
      getFillColor: (f: { properties: { id: string } }) =>
        f.properties.id === selectedAoiId ? ACCENT_FILL : MUTED_FILL,
      lineWidthUnits: "pixels",
      getLineWidth: 1.5,
      onClick: (info) => {
        const props = info.object?.properties as { id: string } | undefined;
        if (props) {
          setSelectedAoiId(props.id);
          setInspectorTarget({ kind: "aoi", id: props.id });
        }
      },
    });

    const drawLayer = new EditableGeoJsonLayer({
      id: "aoi-draw-layer",
      data: draftGeometry
        ? {
            type: "FeatureCollection",
            features: [{ type: "Feature", geometry: draftGeometry, properties: {} }],
          }
        : EMPTY_FEATURE_COLLECTION,
      mode: isDrawing ? new DrawPolygonMode() : new ViewMode(),
      selectedFeatureIndexes: [],
      onEdit: ({ updatedData }) => {
        const feature = updatedData.features[updatedData.features.length - 1];
        if (feature) setDraftGeometry(feature.geometry as unknown as typeof draftGeometry);
      },
      getLineColor: ACCENT_LINE,
      getFillColor: ACCENT_FILL,
      lineWidthUnits: "pixels",
      getLineWidth: 1.5,
      // Vertex handles: 9px accent squares with a glow, per spec.
      editHandlePointRadiusUnits: "pixels",
      getEditHandlePointRadius: 5,
      getEditHandlePointColor: [6, 8, 11, 230],
      getEditHandlePointOutlineColor: ACCENT_LINE,
      editHandlePointOutline: true,
      editHandlePointStrokeWidth: 1.5,
    });

    // Detections: red, pulsing, outlined in the shape of each detection box.
    // Alpha follows the shared pulse level (a smooth cosine breathe). The
    // selected box holds a steady bright highlight.
    const detectionAlpha = Math.round(255 * pulseLevel);
    const detectionsLayer = new GeoJsonLayer({
      id: "detections",
      data: {
        type: "FeatureCollection",
        features: detectionsVisible
          ? (detections ?? []).map((d) => ({
              type: "Feature" as const,
              geometry: d.bbox,
              properties: { id: d.id, label: d.label, score: d.score },
            }))
          : [],
      },
      pickable: true,
      stroked: true,
      filled: true,
      getLineColor: (f: { properties: { id: string } }) =>
        inspectorTarget?.kind === "detection" && inspectorTarget.id === f.properties.id
          ? DETECTION_SELECTED_LINE
          : ([...DETECTION_RED, detectionAlpha] as [number, number, number, number]),
      // Faint red wash so the box still reads as a detection at the dim end of
      // the pulse; the outline is what carries the shape.
      getFillColor: [...DETECTION_RED, Math.round(detectionAlpha * 0.18)] as [number, number, number, number],
      lineWidthUnits: "pixels",
      getLineWidth: 2,
      updateTriggers: {
        getLineColor: [pulseLevel, inspectorTarget],
        getFillColor: [pulseLevel],
      },
      onClick: (info) => {
        const props = info.object?.properties as { id: string } | undefined;
        if (props) setInspectorTarget({ kind: "detection", id: props.id });
      },
    });

    overlay.setProps({ layers: [graticuleLayer, savedAoisLayer, drawLayer, detectionsLayer] });
  }, [
    aois,
    selectedAoiId,
    draftGeometry,
    isDrawing,
    detections,
    detectionsVisible,
    inspectorTarget,
    pulseLevel,
    viewState,
    setSelectedAoiId,
    setDraftGeometry,
    setInspectorTarget,
  ]);

  // Raster imagery: whichever single raster layer is active (mutually
  // exclusive — see LayersControl) at its own configured opacity.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const syncRasterLayer = (
      id: string,
      url: string | null,
      visible: boolean,
      opacity: number,
      beforeId?: string,
    ) => {
      const sourceId = `${id}-source`;
      if (!visible || !url) {
        if (map.getLayer(id)) map.removeLayer(id);
        if (map.getSource(sourceId)) map.removeSource(sourceId);
        delete rasterSourceUrls.current[sourceId];
        return;
      }
      // The source exists but was built for a different scene/analysis (its URL
      // changed) — tear it down so it's re-created below with the new URL.
      if (map.getSource(sourceId) && rasterSourceUrls.current[sourceId] !== url) {
        if (map.getLayer(id)) map.removeLayer(id);
        map.removeSource(sourceId);
        delete rasterSourceUrls.current[sourceId];
      }
      if (!map.getSource(sourceId)) {
        // minzoom is forced to the map's own floor, overriding whatever the
        // tilejson advertises (BRIEF v2, found for real): a Sentinel-2
        // true-color COG's tilejson reports minzoom 8 (derived from its
        // overview count), so MapLibre wouldn't request a single tile below
        // Z8 — imagery stayed blank at exactly the regional zooms you
        // navigate and draw at, even though the tiler happily renders those
        // tiles on request (verified: z5/z6/z7 all return real imagery).
        // NDVI's tilejson already reports minzoom 0, which is why it showed
        // and true-color didn't — this closes that asymmetry.
        map.addSource(sourceId, { type: "raster", url, tileSize: 256, minzoom: MIN_ZOOM });
        rasterSourceUrls.current[sourceId] = url;
      }
      if (!map.getLayer(id)) {
        map.addLayer(
          {
            id,
            type: "raster",
            source: sourceId,
            // fade-duration 0: tiles pop in the instant they arrive instead of
            // cross-fading over ~300ms — makes panning feel markedly snappier
            // (there's no basemap under them for a fade to smooth over anyway).
            // No opacity transition: the change overlay's pulse is already
            // smooth because the rAF loop feeds it a continuous level; a
            // MapLibre transition on top would lag behind those updates.
            paint: { "raster-opacity": opacity, "raster-fade-duration": 0 },
          },
          beforeId && map.getLayer(beforeId) ? beforeId : undefined,
        );
      } else {
        map.setPaintProperty(id, "raster-opacity", opacity);
      }
    };

    const applyLayers = () => {
      const visualHref = selectedScene?.assets.visual?.href;
      const trueColorUrl = visualHref ? trueColorTilejsonUrl(visualHref) : null;
      const ndviUrl = selectedScene?.self_href ? ndviTilejsonUrl(selectedScene.self_href) : null;
      const changeUrl = activeAnalysis?.tilejson_url ?? null;

      // Every raster layer here is served by the tiler, which 401s any
      // request without the token — and MapLibre never retries a source
      // whose tilejson fetch failed. Deferring until the token exists (this
      // effect re-runs when it arrives — tilerToken is a subscribed dep)
      // beats adding a permanently-broken source. Found for real (BRIEF
      // v1.8): auto-scene-selection made scene selection reliably FASTER
      // than the auth bootstrap's tiler-token fetch, so the source was
      // added tokenless and every layer stayed black despite everything
      // else working.
      const tilerReady = Boolean(tilerToken);

      // Base imagery (mutually exclusive) is inserted BENEATH the change
      // overlay so Change stacks on top of it — selecting Change no longer
      // blanks the imagery; True Color / NDVI stays on underneath.
      syncRasterLayer(
        "true-color-layer",
        trueColorUrl,
        tilerReady && activeRasterLayer === "true_color",
        rasterOpacity.true_color,
        "change-layer",
      );
      syncRasterLayer(
        "ndvi-layer",
        ndviUrl,
        tilerReady && activeRasterLayer === "ndvi",
        rasterOpacity.ndvi,
        "change-layer",
      );
      // Change is an independent overlay now (not part of the base radio),
      // gated on its own visibility toggle. Its live opacity is driven by the
      // pulse effect below, so we seed it here at the current pulse level.
      syncRasterLayer("change-layer", changeUrl, tilerReady && changeVisible, rasterOpacity.change * pulseLevel);
    };

    if (map.isStyleLoaded()) {
      applyLayers();
    } else {
      map.once("load", applyLayers);
    }
    // pulseLevel is intentionally NOT a dep — re-adding sources every frame
    // would be wasteful; the dedicated pulse effect below nudges only opacity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedScene, activeAnalysis, activeRasterLayer, changeVisible, rasterOpacity, tilerToken]);

  // Drives the Change overlay's pulse by nudging only its raster-opacity — a
  // cheap paint-property update (the layer's own opacity transition eases it),
  // no source add/remove. Runs off the same shared pulse phase as the detection
  // boxes so the two breathe together.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getLayer("change-layer")) return;
    map.setPaintProperty("change-layer", "raster-opacity", rasterOpacity.change * pulseLevel);
  }, [pulseLevel, changeVisible, rasterOpacity, activeAnalysis]);

  return (
    <>
      <div ref={containerRef} className="map-canvas" />
      {/* BRIEF v2, found for real, repeatedly, across this entire project's
          live testing history: there's no basemap here by design (see
          CLAUDE.md's air-gap invariant), so a solid black map is the
          correct rendering of "nothing selected yet" -- but it's also
          exactly what a genuinely broken/failed-to-load state looks like.
          Nothing ever distinguished the two before. */}
      {!selectedScene && (
        <div className="map-empty-hint">
          <div className="map-empty-hint-inner">
            <div className="map-empty-hint-title">No imagery loaded</div>
            <div className="map-empty-hint-body">
              This map has no basemap of its own — select an AOI on the left,
              or draw a new one, to load real imagery here.
            </div>
          </div>
        </div>
      )}
      {selectedScene && tilesLoading && (
        <div className="map-loading-chip">
          <span className="spinner" />
          LOADING IMAGERY
        </div>
      )}
    </>
  );
}
