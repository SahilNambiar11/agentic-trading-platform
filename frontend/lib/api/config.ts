const LOCAL_API_BASE_URL = "http://127.0.0.1:8000";

export function getApiBaseUrl(): string {
  const configuredUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();

  if (configuredUrl) {
    return configuredUrl.replace(/\/$/, "");
  }

  if (process.env.NODE_ENV === "production") {
    throw new Error(
      "NEXT_PUBLIC_API_BASE_URL must be configured for production builds and runtime.",
    );
  }

  return LOCAL_API_BASE_URL;
}
