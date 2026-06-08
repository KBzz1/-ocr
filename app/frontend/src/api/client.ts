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

export function parseErrorBody(body: unknown, status: number, fallbackMessage = '请求失败', fallbackCode = 'UNKNOWN_ERROR'): ApiError {
  if (isObject(body) && isObject(body.error)) {
    const code = typeof body.error.code === 'string' ? body.error.code : fallbackCode;
    const message = typeof body.error.message === 'string' ? body.error.message : fallbackMessage;
    const details = isObject(body.error.details) ? body.error.details : {};
    return new ApiError(message, code, status, details);
  }

  return new ApiError(fallbackMessage, fallbackCode, status);
}

export function getApiErrorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export interface ApiRequestOptions extends RequestInit {
  /** 请求超时(毫秒)。0 或负数表示不超时(长任务使用)。默认 8000。 */
  timeoutMs?: number;
}

export async function apiRequest<T>(path: string, init?: ApiRequestOptions): Promise<T> {
  const { timeoutMs = 8000, signal: callerSignal, ...requestInit } = init ?? {};
  const inBrowser = !navigator.userAgent.toLowerCase().includes('jsdom');
  const canUseTimeoutSignal = inBrowser && timeoutMs > 0;
  const controller = canUseTimeoutSignal ? new AbortController() : null;
  const timeoutId = controller ? window.setTimeout(() => controller.abort(), timeoutMs) : null;
  const headers = new Headers(requestInit.headers);
  headers.set('Accept', 'application/json');
  const requestUrl = new URL(path, window.location.origin).toString();
  const fetchInit: RequestInit = {
    ...requestInit,
    headers
  };

  // jsdom 的 fetch 对 AbortSignal 做了跨 realm 校验,跨实例的 signal 直接抛错;
  // 测试环境统一不传 signal,生产环境优先用调用方传入的 signal(支持取消),其次用超时 controller。
  if (inBrowser) {
    if (callerSignal) {
      fetchInit.signal = callerSignal;
    } else if (controller) {
      fetchInit.signal = controller.signal;
    }
  }

  const response = await fetch(requestUrl, fetchInit).finally(() => {
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
