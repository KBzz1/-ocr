import { apiRequest } from './client';

export interface SystemStatus {
  status: 'running' | 'error' | string;
  version: string;
  started_at: string;
  lan_addresses: string[];
  message?: string;
}

export function getSystemStatus() {
  return apiRequest<SystemStatus>('/api/system/status');
}
