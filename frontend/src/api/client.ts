import axios from "axios";

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000",
  timeout: 10000,
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status || 500;
    const message =
      error.response?.data?.detail || error.message || "An unknown error occurred";
    return Promise.reject({ status, message });
  }
);
