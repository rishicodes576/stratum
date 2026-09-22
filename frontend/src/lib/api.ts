export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : Array.isArray(body.detail)
          ? body.detail.map((d: { msg: string }) => d.msg).join("; ")
          : "The request could not be completed";
    throw new ApiError(detail, response.status);
  }
  return body as T;
}

export function relativeTime(value: string) {
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : value + "Z";
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(normalized).getTime()) / 60000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h ago`;
  return `${Math.floor(minutes / 1440)}d ago`;
}
