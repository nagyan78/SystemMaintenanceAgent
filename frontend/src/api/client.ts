export type ApiErrorPayload = {
  error_code?: string;
  message?: string;
};

export class ApiError extends Error {
  status: number;
  payload: ApiErrorPayload | string | null;

  constructor(status: number, payload: ApiErrorPayload | string | null) {
    const message =
      typeof payload === "object" && payload?.message
        ? payload.message
        : `请求失败 (${status})`;
    super(message);
    this.status = status;
    this.payload = payload;
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(path, options);
  const contentType = response.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const detail = typeof body === "object" && body !== null ? body.detail : body;
    if (response.status === 500 && (!detail || detail === "Internal Server Error")) {
      throw new ApiError(response.status, { message: "后端服务未连接" });
    }
    throw new ApiError(response.status, detail);
  }

  return body as T;
}
