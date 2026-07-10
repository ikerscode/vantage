import { DrawPolygonMode, EditableGeoJsonLayer, ViewMode } from "@deck.gl-community/editable-layers";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { GeoJsonLayer } from "deck.gl";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";

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

// Observation, not engagement — nothing here reads as targeting (no
// crosshairs, no lock-on, no red target boxes). One accent (cyan) for
// chrome/selection; detections are neutral off-white, opacity = confidence.
const ACCENT_LINE: [number, number, number, number] = [63, 184, 212, 255];
const ACCENT_FILL: [number, number, number, number] = [63, 184, 212, 36];
const MUTED_LINE: [number, number, number, number] = [139, 148, 158, 160];
const MUTED_FILL: [number, number, number, number] = [139, 148, 158, 18];
const DETECTION_SELECTED_LINE: [number, number, number, number] = [95, 211, 238, 255];

const EMPTY_FEATURE_COLLECTION = { type: "FeatureCollection" as const, features: [] };

export function MapCanvas() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);

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

  // Initialize the map + deck.gl overlay once.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: darkVoidStyle,
      center: [viewState.longitude, viewState.latitude],
      zoom: viewState.zoom,
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
    mapRef.current.flyTo({
      center: [flyToRequest.longitude, flyToRequest.latitude],
      zoom: flyToRequest.zoom ?? mapRef.current.getZoom(),
      essential: true,
    });
    clearFlyToRequest();
  }, [flyToRequest, clearFlyToRequest]);

  // BRIEF v2, found for real: MapLibre's own dragPan/doubleClickZoom
  // handlers consume the mousedown/dblclick before deck.gl's
  // EditableGeoJsonLayer ever sees it (a well-documented deck.gl+Mapbox/
  // MapLibre integration limitation, not a bug in our layer config —
  // MapboxOverlay only forwards a subset of pointer events to deck.gl,
  // and does so AFTER the base map's own handlers have already acted on
  // them). Without this, clicking to add a vertex just pans the map
  // instead. Disabling both while drawing (and double-click, which
  // DrawPolygonMode uses to finish a ring) is the standard fix.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (isDrawing) {
      map.dragPan.disable();
      map.doubleClickZoom.disable();
    } else {
      map.dragPan.enable();
      map.doubleClickZoom.enable();
    }
  }, [isDrawing]);

  // Vector layers: saved AOIs, the in-progress AOI draw layer, detection boxes.
  useEffect(() => {
    const overlay = overlayRef.current;
    if (!overlay) return;

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
      filled: false,
      getLineColor: (f: { properties: { id: string; score: number } }) =>
        inspectorTarget?.kind === "detection" && inspectorTarget.id === f.properties.id
          ? DETECTION_SELECTED_LINE
          : ([230, 237, 243, Math.round(f.properties.score * 255)] as [number, number, number, number]),
      lineWidthUnits: "pixels",
      getLineWidth: 1.5,
      onClick: (info) => {
        const props = info.object?.properties as { id: string } | undefined;
        if (props) setInspectorTarget({ kind: "detection", id: props.id });
      },
    });

    overlay.setProps({ layers: [savedAoisLayer, drawLayer, detectionsLayer] });
  }, [
    aois,
    selectedAoiId,
    draftGeometry,
    isDrawing,
    detections,
    detectionsVisible,
    inspectorTarget,
    setSelectedAoiId,
    setDraftGeometry,
    setInspectorTarget,
  ]);

  // Raster imagery: whichever single raster layer is active (mutually
  // exclusive — see LayersControl) at its own configured opacity.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const syncRasterLayer = (id: string, url: string | null, visible: boolean, opacity: number) => {
      const sourceId = `${id}-source`;
      if (!visible || !url) {
        if (map.getLayer(id)) map.removeLayer(id);
        if (map.getSource(sourceId)) map.removeSource(sourceId);
        return;
      }
      if (!map.getSource(sourceId)) {
        map.addSource(sourceId, { type: "raster", url, tileSize: 256 });
      }
      if (!map.getLayer(id)) {
        map.addLayer({ id, type: "raster", source: sourceId, paint: { "raster-opacity": opacity } });
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

      syncRasterLayer(
        "true-color-layer",
        trueColorUrl,
        tilerReady && activeRasterLayer === "true_color",
        rasterOpacity.true_color,
      );
      syncRasterLayer("ndvi-layer", ndviUrl, tilerReady && activeRasterLayer === "ndvi", rasterOpacity.ndvi);
      syncRasterLayer("change-layer", changeUrl, tilerReady && activeRasterLayer === "change", rasterOpacity.change);
    };

    if (map.isStyleLoaded()) {
      applyLayers();
    } else {
      map.once("load", applyLayers);
    }
  }, [selectedScene, activeAnalysis, activeRasterLayer, rasterOpacity, tilerToken]);

  return <div ref={containerRef} className="map-canvas" />;
}
