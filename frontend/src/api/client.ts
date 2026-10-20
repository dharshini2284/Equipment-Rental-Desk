import type { ApiErrorBody } from "./types";
import { getClockOverride } from "../lib/clock";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

/** An error response from the API, or a network failure dressed up as one. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly requestId: string | null;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.status = status;
    this.code = body.code;
    this.details = body.details;
    this.requestId = body.request_id;
  }

  /** Field-level messages from a validation error, e.g. "body.amount_paise: ...". */
  get fieldMessages(): string[] {
    const fields = this.details.fields;
    if (!Array.isArray(fields)) return [];
    return fields.map((f: { field: string; message: string }) => `${f.field}: ${f.message}`);
  }

  /** Every borrowing block reported with a rule violation. */
  get blockMessages(): string[] {
    const blocks = this.details.blocks;
    if (!Array.isArray(blocks)) return [];
    return blocks.map((b: { message: string }) => b.message);
  }
}

function isErrorBody(value: unknown): value is { error: ApiErrorBody } {
  return typeof value === "object" && value !== null && "error" in value;
}

type Query = Record<string, string | number | undefined | null>;

function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const search = params.toString();
  return `${API_BASE_URL}/api/v1${path}${search ? `?${search}` : ""}`;
}

type Method = "GET" | "POST" | "PATCH" | "DELETE";

async function send(
  method: Method,
  path: string,
  options: { body?: unknown; query?: Query },
): Promise<Response> {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const clock = getClockOverride();
  if (clock) headers["X-Test-Clock"] = clock;
  try {
    return await fetch(buildUrl(path, options.query), {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw new ApiError(0, {
      type: "network",
      code: "NETWORK_ERROR",
      message:
        "Could not reach the server. If it is on a free host it may be waking up; try again in a minute.",
      details: {},
      request_id: null,
    });
  }
}

async function errorFrom(response: Response): Promise<ApiError> {
  const payload: unknown = await response.json().catch(() => null);
  if (isErrorBody(payload)) return new ApiError(response.status, payload.error);
  return new ApiError(response.status, {
    type: "unknown",
    code: "UNEXPECTED_RESPONSE",
    message: `The server answered with status ${response.status}.`,
    details: {},
    request_id: response.headers.get("X-Request-ID"),
  });
}

export async function request<T>(
  method: Method,
  path: string,
  options: { body?: unknown; query?: Query } = {},
): Promise<T> {
  const response = await send(method, path, options);
  if (response.status === 204) return undefined as T;
  if (!response.ok) throw await errorFrom(response);
  return (await response.json()) as T;
}

/** Fetch a file (e.g. a PDF) and hand it to the browser as a download. */
export async function download(path: string, fallbackName: string): Promise<void> {
  const response = await send("GET", path, {});
  if (!response.ok) throw await errorFrom(response);
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  // Revoking straight away can cancel the download in some browsers; give it time to start.
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
