import { describe, expect, it } from 'vitest';

import {
  appRoutes,
  buildMobileUploadPath,
  buildPatientPath,
  buildReviewPath,
  buildTaskExportPath
} from './routes';

describe('frontend route skeleton', () => {
  it('uses task-bound mobile upload route', () => {
    expect(appRoutes.workstation.path).toBe('/');
    expect(appRoutes.mobileCapture.path).toBe('/mobile/upload/:taskId');
    expect(appRoutes.review.path).toBe('/review');
    expect(buildMobileUploadPath('task_001')).toBe('/mobile/upload/task_001');
  });

  it('does not expose mobile session route helpers', () => {
    const routePaths = Object.values(appRoutes).map((route) => route.path);
    expect(routePaths).not.toContain('/mobile/sessions/:sessionId');
    expect(buildReviewPath('task/001')).toBe('/tasks/task%2F001/review');
    expect(buildTaskExportPath('task/001')).toBe('/tasks/task%2F001/export');
  });

  it('exposes the patients management route and encodes patient ids', () => {
    expect(appRoutes.patients.path).toBe('/patients');
    expect(buildPatientPath('P/A')).toBe('/patients/P%2FA');
    expect(buildPatientPath('P-A1B2C3D4')).toBe('/patients/P-A1B2C3D4');
  });
});
