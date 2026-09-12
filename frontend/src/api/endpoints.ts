import { apiClient } from "./client";
import {
  PlantsResponse,
  Plant,
  ForecastResponse,
  DashboardResponse,
  DSMResponse,
  DSMRequest,
  OptimizeResponse,
  OptimizeRequest,
  PoolingResponse,
  PoolingRequest,
  RAGQueryResponse,
  RAGQueryRequest,
  HealthResponse,
} from "../types/api";

// Every function takes an optional AbortSignal and forwards it to axios, so a
// superseded request is actually cancelled at the transport layer rather than merely
// ignored on arrival. Sprint 7's rapid slider/toggle is the case this pays for.

export const getPlants = async (signal?: AbortSignal): Promise<PlantsResponse> => {
  const { data } = await apiClient.get<PlantsResponse>("/plants", { signal });
  return data;
};

export const getPlant = async (id: string, signal?: AbortSignal): Promise<Plant> => {
  const { data } = await apiClient.get<Plant>(`/plants/${id}`, { signal });
  return data;
};

export const getForecast = async (
  plantId: string,
  date?: string,
  signal?: AbortSignal
): Promise<ForecastResponse> => {
  const { data } = await apiClient.get<ForecastResponse>("/forecast", {
    params: { plant_id: plantId, ...(date ? { date } : {}) },
    signal,
  });
  return data;
};

export const getDashboard = async (
  plantId: string,
  date?: string,
  signal?: AbortSignal
): Promise<DashboardResponse> => {
  const { data } = await apiClient.get<DashboardResponse>(
    `/dashboard/${encodeURIComponent(plantId)}`,
    { params: date ? { date } : undefined, signal }
  );
  return data;
};

export const postDsm = async (
  body: DSMRequest,
  signal?: AbortSignal
): Promise<DSMResponse> => {
  const { data } = await apiClient.post<DSMResponse>("/dsm", body, { signal });
  return data;
};

export const postOptimize = async (
  body: OptimizeRequest,
  signal?: AbortSignal
): Promise<OptimizeResponse> => {
  const { data } = await apiClient.post<OptimizeResponse>("/optimize", body, { signal });
  return data;
};

export const postPooling = async (
  body: PoolingRequest,
  signal?: AbortSignal
): Promise<PoolingResponse> => {
  const { data } = await apiClient.post<PoolingResponse>("/pooling", body, { signal });
  return data;
};

export const postRagQuery = async (
  body: RAGQueryRequest,
  signal?: AbortSignal
): Promise<RAGQueryResponse> => {
  const { data } = await apiClient.post<RAGQueryResponse>("/rag/query", body, { signal });
  return data;
};

export const getHealth = async (signal?: AbortSignal): Promise<HealthResponse> => {
  const { data } = await apiClient.get<HealthResponse>("/health", { signal });
  return data;
};

/** Corpus + LLM readiness. Shape is diagnostic and varies — keep it loose. */
export const getRagHealth = async (
  signal?: AbortSignal
): Promise<Record<string, unknown>> => {
  const { data } = await apiClient.get<Record<string, unknown>>("/rag/health", { signal });
  return data;
};
