import { useMemo } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { usePlants } from "../../hooks/usePlants";
import { Plant } from "../../types/api";

// Leaflet's own renderer (canvas/SVG path) will not resolve a CSS variable string —
// it needs a concrete colour. Resolve the design tokens once, from the DOM, rather
// than hardcoding a hex literal here.
const readToken = (name: string, fallback: string): string => {
  if (typeof document === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
};

const SOLAR_COLOR = readToken("--color-solar", "#F5B33C");
const WIND_COLOR = readToken("--color-wind", "#5EC8C8");
const ACCENT_COLOR = readToken("--color-accent", "#CFF245");

const GUJARAT_CENTER: [number, number] = [23.2, 71.0];
const GUJARAT_ZOOM = 7;
// Locks pan/zoom to Gujarat — [[south, west], [north, east]]. Padded a little past
// the state border so the plants near it (Kutch, Palanpur) aren't flush with the edge.
const GUJARAT_BOUNDS: [[number, number], [number, number]] = [
  [19.5, 67.5],
  [25.5, 75.0],
];

const DARK_TILE_URL = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
const DARK_TILE_ATTRIBUTION =
  '&copy; OpenStreetMap contributors &copy; CARTO';

const colorFor = (type: Plant["type"]): string => (type === "solar" ? SOLAR_COLOR : WIND_COLOR);

// 6..18 px, scaled by capacity so a 75 MW plant reads visibly larger than a 30 MW one.
const radiusFor = (avcMw: number): number => Math.min(18, Math.max(6, 6 + avcMw / 12));

interface Props {
  selectedPlantId?: string;
  onSelectPlant?: (plantId: string) => void;
}

export default function PlantMap({ selectedPlantId, onSelectPlant }: Props) {
  const { data, loading, error } = usePlants();

  const plants = useMemo(() => data?.plants ?? [], [data]);

  if (loading) {
    return (
      <div className="h-[360px] w-full animate-pulse rounded-[var(--radius-card)] border border-border bg-surface-2" />
    );
  }

  if (error) {
    return (
      <div className="flex h-[360px] w-full items-center justify-center rounded-[var(--radius-card)] border border-border bg-surface text-sm text-text-muted">
        Could not load plant locations.
      </div>
    );
  }

  if (plants.length === 0) {
    return (
      <div className="flex h-[360px] w-full items-center justify-center rounded-[var(--radius-card)] border border-border bg-surface text-sm text-text-muted">
        No plants to show.
      </div>
    );
  }

  return (
    <div className="w-full max-w-full overflow-hidden rounded-[var(--radius-card)] border border-border bg-surface">
      <div className="h-[360px] w-full">
        <MapContainer
          center={GUJARAT_CENTER}
          zoom={GUJARAT_ZOOM}
          minZoom={GUJARAT_ZOOM}
          maxBounds={GUJARAT_BOUNDS}
          maxBoundsViscosity={1.0}
          scrollWheelZoom={false}
          style={{ height: "100%", width: "100%" }}
        >
          <TileLayer
            url={DARK_TILE_URL}
            attribution={DARK_TILE_ATTRIBUTION}
          />
          {plants.map((plant) => {
            const isSelected = plant.id === selectedPlantId;
            return (
              <CircleMarker
                key={plant.id}
                center={[plant.lat, plant.lon]}
                radius={radiusFor(plant.avc_mw)}
                pathOptions={{
                  color: isSelected ? ACCENT_COLOR : colorFor(plant.type),
                  fillColor: isSelected ? ACCENT_COLOR : colorFor(plant.type),
                  fillOpacity: isSelected ? 0.9 : 0.7,
                  weight: isSelected ? 3 : 1.5,
                }}
                eventHandlers={{
                  click: (e) => {
                    // Stop Leaflet from propagating the click to the map,
                    // which can cause unwanted side effects.
                    e.originalEvent.stopPropagation();
                    e.originalEvent.preventDefault();
                    onSelectPlant?.(plant.id);
                  },
                }}
              >
                <Popup>
                  <div className="text-sm">
                    <div className="font-semibold">{plant.name}</div>
                    <div>Type: {plant.type === "solar" ? "Solar" : "Wind"}</div>
                    <div>{plant.avc_mw} MW</div>
                    <div>Pool: {plant.pool_id ?? "—"}</div>
                    <div>
                      {plant.lat.toFixed(3)}, {plant.lon.toFixed(3)}
                    </div>
                  </div>
                </Popup>
              </CircleMarker>
            );
          })}
        </MapContainer>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border px-4 py-2 text-xs text-text-muted">
        <span className="flex items-center gap-2">
          <span
            className="inline-block h-2.5 w-2.5 rounded-full"
            style={{ background: "var(--color-solar)" }}
          />
          Solar
        </span>
        <span className="flex items-center gap-2">
          <span
            className="inline-block h-2.5 w-2.5 rounded-full"
            style={{ background: "var(--color-wind)" }}
          />
          Wind
        </span>
        {selectedPlantId && (
          <span className="flex items-center gap-2">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ background: "var(--color-accent)" }}
            />
            Selected
          </span>
        )}
        {/* Required by the data licences: OpenStreetMap is ODbL and the WRI Global
            Power Plant Database is CC-BY 4.0. Both oblige visible credit wherever
            the plant records are shown. Keep this line when editing the legend. */}
        <span className="ml-auto text-right text-[11px] leading-tight">
          Plant data © OpenStreetMap contributors (ODbL) · WRI Global Power Plant Database (CC-BY 4.0)
        </span>
      </div>
    </div>
  );
}
