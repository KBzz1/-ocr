import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { UserFriendlyError } from './UserFriendlyError';

describe('UserFriendlyError', () => {
  it('shows understandable common recovery messages', () => {
    render(<UserFriendlyError code="MOBILE_CONNECTION_FAILED" />);

    expect(screen.getByRole('alert').textContent).toContain(
      '无法连接到工作站，请确认手机与电脑在同一网络'
    );
  });

  it('does not expose stack traces, full medical text, base64 payloads or paths', () => {
    render(
      <UserFriendlyError
        code="EXPORT_FAILED"
        message="Traceback: /secret/model.log 完整病历原文 data:image/png;base64,AAAA 500"
      />
    );

    const text = screen.getByRole('alert').textContent ?? '';
    expect(text).toContain('导出失败');
    expect(text).not.toContain('Traceback');
    expect(text).not.toContain('/secret/model.log');
    expect(text).not.toContain('完整病历原文');
    expect(text).not.toContain('base64');
  });
});
