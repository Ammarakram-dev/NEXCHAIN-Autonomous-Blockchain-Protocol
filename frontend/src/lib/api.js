const API_BASE = "/api/v1";

async function request(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(options.headers || {}),
      },
    });

    const text = await response.text();

    let data;

    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = { raw: text };
    }

    if (!response.ok) {
      throw new Error(
        data?.detail ||
          data?.reason ||
          data?.message ||
          `API request failed: ${response.status}`
      );
    }

    return data;
  } finally {
    clearTimeout(timeout);
  }
}

export const nexchainAPI = {
  health: () => request("/health"),

  status: () => request("/status"),

  blocks: () => request("/blocks"),

  selfTest: () =>
    request("/self-test", {
      method: "POST",
    }),
};