type ErrorLike = {
  code?: string;
  message?: string;
  details?: Record<string, unknown>;
};

const safeMessages: Record<string, string> = {
  ALGORITHM_MODULE_NOT_CONFIGURED: '处理模块未配置，请检查本地服务配置后重试。',
  REVIEW_VALIDATION_FAILED: '审核结果尚未满足确认条件，请检查未审核、存疑或为空字段。',
  EXPORT_FAILED: '导出失败，请稍后重试。',
  INVALID_TASK_TRANSITION: '当前任务状态不允许执行该操作。',
  INVALID_RESPONSE_SHAPE: '服务响应格式不正确，请重试。'
};

export function normalizeApiError(error: ErrorLike | unknown) {
  if (typeof error === 'object' && error !== null && 'code' in error) {
    const code = String((error as ErrorLike).code ?? '');
    if (code in safeMessages) {
      return safeMessages[code];
    }
  }

  return '操作失败，请重试。';
}
