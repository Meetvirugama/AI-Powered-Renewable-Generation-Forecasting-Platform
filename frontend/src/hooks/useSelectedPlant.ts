import { usePlants } from "./usePlants";
import type { Plant } from "../types/api";

/**
 * DashboardResponse carries only plant_id/plant_name/avc_mw — it does not include
 * `type` or `pool_id`. Pages that need the plant's asset type (for its CERC tolerance
 * band) or pool_id (to call POST /pooling) look it up here from the plant list.
 */
export function useSelectedPlant(plantId: string): Plant | null {
  const { data } = usePlants();
  return data?.plants.find((p) => p.id === plantId) ?? null;
}
