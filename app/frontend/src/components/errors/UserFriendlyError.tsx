type KnownErrorCode =
  | 'MOBILE_CONNECTION_FAILED'
  | 'UPLOAD_FAILED'
  | 'IMAGE_TOO_LARGE'
  | 'TASK_PROCESSING_FAILED'
  | 'FIELD_EXTRACTION_FAILED'
  | 'REVIEW_VALIDATION_FAILED'
  | 'EXPORT_FAILED'
  | 'ALGORITHM_MODULE_NOT_CONFIGURED'
  | string;

const safeMessages: Record<string, string> = {
  MOBILE_CONNECTION_FAILED: '无法连接到工作站，请确认手机与电脑在同一网络',
  UPLOAD_FAILED: '图片上传失败，请检查照片后重试',
  IMAGE_TOO_LARGE: '图片过大，请重新拍摄或压缩后上传',
  TASK_PROCESSING_FAILED: '任务处理失败，请查看原因后重新处理',
  FIELD_EXTRACTION_FAILED: '字段抽取失败，请重新处理任务',
  REVIEW_VALIDATION_FAILED: '请先确认审核，检查未审核、存疑或为空字段',
  EXPORT_FAILED: '导出失败，请先确认审核或稍后重试',
  ALGORITHM_MODULE_NOT_CONFIGURED: '处理模块未配置，请检查本地服务配置后重试'
};

function sanitizeMessage(message: string) {
  const unsafePatterns = [
    /traceback[\s\S]*/i,
    /data:image\/[^;\s]+;base64,[^\s]+/gi,
    /base64[^\s]*/gi,
    /\/[^\s]+/g,
    /[A-Za-z]:\\[^\s]+/g,
    /完整病历原文/g,
    /身份证号?[：: ]?\d{6,}/g,
    /模型输出全文/g
  ];

  return unsafePatterns.reduce((safe, pattern) => safe.replace(pattern, ''), message).trim();
}

export interface UserFriendlyErrorProps {
  code?: KnownErrorCode;
  message?: string;
  title?: string;
}

export function getUserFriendlyErrorMessage(code?: KnownErrorCode, message?: string) {
  if (code && safeMessages[code]) {
    return safeMessages[code];
  }

  const sanitized = message ? sanitizeMessage(message) : '';
  return sanitized || '操作失败，请重试';
}

export function UserFriendlyError({ code, message, title }: UserFriendlyErrorProps) {
  const safeMessage = getUserFriendlyErrorMessage(code, message);
  const messageWithoutRepeatedTitle =
    title && safeMessage.startsWith(title)
      ? safeMessage.slice(title.length).replace(/^[，,:：\s]+/, '')
      : safeMessage;

  return (
    <div role="alert" aria-live="polite">
      {title ? <strong>{title}</strong> : null}
      <span>{title ? `：${messageWithoutRepeatedTitle}` : safeMessage}</span>
    </div>
  );
}
