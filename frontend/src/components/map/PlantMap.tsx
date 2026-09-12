import { useEffect, useMemo } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from "react-leaflet";
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

// Only used when bounds cannot be computed -- an empty list, or every plant at
// one point. The real view is fitted to the data below.
const GUJARAT_CENTER: [number, number] = [23.2, 71.0];
const GUJARAT_ZOOM = 7;

/**
 * Frame the map on the plants that were actually returned.
 *
 * A fixed centre and zoom was right for four plants placed by hand. The real
 * inventory runs from Kutch in the far west to Surat in the south, and a
 * hardcoded viewport either clips it or leaves the state floating in empty sea.
 * Fitting the bounds also means the component keeps working unchanged if the
 * corpus is ever imported for another state.
 */
function FitToPlants({ plants }: { plants: Plant[] }) {
  const map = useMap();

  useEffect(() => {
    if (plants.length === 0) return;
    if (plants.length === 1) {
      map.setView([plants[0].lat, plants[0].lon], 9);
      return;
    }
    const bounds: [number, number][] = plants.map((p) => [p.lat, p.lon]);
    map.fitBounds(bounds, { padding: [28, 28], maxZoom: 9 });
  }, [map, plants]);

  return null;
}

const DARK_TILE_URL = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
const DARK_TILE_ATTRIBUTION =
  '&copy; OpenStreetMap contributors &copy; CARTO';

const colorFor = (type: Plant["type"]): string => (type === "solar" ? SOLAR_COLOR : WIND_COLOR);

// Square-root of capacity, because marker *area* is what the eye compares and
// area grows with the square of the radius — so this makes a 1,000 MW park read
// as roughly ten times the 10 MW one rather than merely bigger.
//
// The previous scale was linear and capped (`6 + avcMw / 12`, max 18px), which
// was fine for four plants between 30 and 75 MW. Against the real inventory it
// saturates: everything above 144 MW rendered identically, so Khavda at 1,000 MW
// looked the same as a 150 MW farm.
const radiusFor = (avcMw: number): number =>
  Math.min(22, Math.max(4, Math.sqrt(Math.max(avcMw, 0)) * 0.75 + 3));

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
          scrollWheelZoom={false}
          style={{ height: "100%", width: "100%" }}
        >
          <TileLayer url={DARK_TILE_URL} attribution={DARK_TILE_ATTRIBUTION} />
          <FitToPlants plants={plants} />
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
                  click: () => onSelectPlant?.(plant.id),
                }}
              >
                <Popup>
                  <div className="text-sm">
                    <div className="font-semibold">{plant.name}</div>
                    <div>Type: {plant.type === "solar" ? "Solar" : "Wind"}</div>
                    <div>{plant.avc_mw} MW</div>
                    <div>Pool: {plant.pool_id ?? "not pooled"}</div>
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
      <div className="flex items-center gap-4 border-t border-border px-4 py-2 text-xs text-text-muted">
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
        {/* Plant records are ODbL (OpenStreetMap) and CC-BY 4.0 (WRI). Both
            licences require this credit wherever the data is shown. */}
        <span className="ml-auto text-right text-[11px] leading-tight text-text-muted">
          Plant data © OpenStreetMap contributors (ODbL) · WRI Global Power Plant
          Database (CC-BY 4.0)
        </span>
      </div>
    </div>
  );
}
