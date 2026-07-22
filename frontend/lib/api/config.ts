const LOCAL_API_BASE_URL = "http://127.0.0.1:8000";

export function getApiBaseUrl(): string {
  // Browser-side API helpers call this before making requests to FastAPI.
  // Local development can use the default, but production must explicitly set
  // the public backend URL so a deployed frontend never guesses an API target.
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
