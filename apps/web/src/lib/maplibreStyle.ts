import type { StyleSpecification } from "maplibre-gl";

/**
 * No external basemap tiles. A hosted vector/raster basemap (Mapbox/MapTiler/
 * OSM demo tiles) is exactly the external-SaaS dependency the air-gap
 * invariant forbids in the core path. This is a dark void — matches the
 * existing --bg palette — not street/terrain detail, which is also just
 * correct for an ISR imagery tool: the content is the raster layers added on
 * top (true color / NDVI / change map), not a street map underneath them.
 */
export const darkVoidStyle: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [
    {
      id: "background",
      type: "background",
      paint: {
        "background-color": "#06080b",
      },
    },
  ],
};
