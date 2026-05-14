export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  };
}

export interface ApiSuccessBody<T> {
  success: true;
  data: T;
}

export class ApiError extends Error {
  code: string;
  details: Record<string, unknown>;
  status: number;

  constructor(message: string, code: string, status: number, details: Record<string, unknown> = {}) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function parseErrorBody(body: unknown, status: number): ApiError {
  if (isObject(body) && isObject(body.error)) {
    const code = typeof body.error.code === 'string' ? body.error.code : 'UNKNOWN_ERROR';
    const message = typeof body.error.message === 'string' ? body.error.message : '请求失败';
    const details = isObject(body.error.details) ? body.error.details : {};
    return new ApiError(message, code, status, details);
  }

  return new ApiError('请求失败', 'UNKNOWN_ERROR', status);
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const canUseTimeoutSignal = !navigator.userAgent.toLowerCase().includes('jsdom');
  const controller = canUseTimeoutSignal ? new AbortController() : null;
  const timeoutId = controller ? window.setTimeout(() => controller.abort(), 8000) : null;
  const headers = new Headers(init?.headers);
  headers.set('Accept', 'application/json');
  const requestUrl = new URL(path, window.location.origin).toString();
  const requestInit: RequestInit = {
    ...init,
    headers
  };

  if (init?.signal) {
    requestInit.signal = init.signal;
  } else if (controller) {
    requestInit.signal = controller.signal;
  }

  const response = await fetch(requestUrl, requestInit).finally(() => {
    if (timeoutId) window.clearTimeout(timeoutId);
  });

  const body = (await response.json().catch(() => null)) as unknown;

  if (!response.ok) {
    throw parseErrorBody(body, response.status);
  }

  if (!isObject(body) || body.success !== true || !('data' in body)) {
    throw new ApiError('服务响应格式不正确', 'INVALID_RESPONSE_SHAPE', response.status);
  }

  return body.data as T;
}
