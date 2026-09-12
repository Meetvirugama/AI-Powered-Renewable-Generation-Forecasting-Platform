import { useState, useEffect, useCallback } from "react";
import { postRagQuery } from "../api/endpoints";
import { RAGQueryResponse, RAGQueryRequest } from "../types/api";
import ragMock from "../mocks/rag.json";

export const useRAG = (body: RAGQueryRequest) => {
  const [data, setData] = useState<RAGQueryResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<unknown>(null);

  const fetchRag = useCallback(async (signal?: AbortSignal) => {
    if (!body || Object.keys(body).length === 0) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      if (import.meta.env.VITE_USE_MOCKS === "true") {
        setData(ragMock as RAGQueryResponse);
      } else {
        const response = await postRagQuery(body, signal);
        if (signal?.aborted) return;
        setData(response);
      }
    } catch (err) {
      if (signal?.aborted) return;
      setError(err);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, /* eslint-disable-next-line react-hooks/exhaustive-deps */
  [JSON.stringify(body)]);

  useEffect(() => {
    const controller = new AbortController();
    fetchRag(controller.signal);
    return () => controller.abort();
  }, [fetchRag]);

  const refetch = () => fetchRag();

  return { data, loading, error, refetch };
};
