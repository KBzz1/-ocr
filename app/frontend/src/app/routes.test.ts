import { describe, expect, it } from 'vitest';

import {
  appRoutes,
  buildMobileSessionPath,
  buildReviewPath,
  buildTaskExportPath
} from './routes';

describe('frontend route skeleton', () => {
  it('defines stable top-level routes for next-stage pages', () => {
    expect(appRoutes.workstation.path).toBe('/');
    expect(appRoutes.mobileCapture.path).toBe('/mobile/sessions/:sessionId');
    expect(appRoutes.tasks.path).toBe('/tasks');
    expect(appRoutes.review.path).toBe('/tasks/:taskId/review');
    expect(appRoutes.export.path).toBe('/tasks/:taskId/export');
  });

  it('builds encoded paths for dynamic routes', () => {
    expect(buildMobileSessionPath('sess 001')).toBe('/mobile/sessions/sess%20001');
    expect(buildReviewPath('task/001')).toBe('/tasks/task%2F001/review');
    expect(buildTaskExportPath('task/001')).toBe('/tasks/task%2F001/export');
  });
});
