import { apiRequest } from './client';
import type { TaskSummary } from './tasks';

export interface PatientRecord {
  patient_id: string;
  name: string;
  gender?: string | null;
  age?: number | null;
  created_at: string;
  updated_at: string;
  deleted_at?: string | null;
}

export interface PatientSummary extends PatientRecord {
  task_count: number;
  latest_record_at?: string | null;
}

export interface PatientRecordGroup {
  document_type: string;
  document_type_label: string;
  tasks: TaskSummary[];
}

export interface PatientDetailResponse {
  patient: PatientRecord;
  record_groups: PatientRecordGroup[];
}

export interface CreatePatientInput {
  name: string;
  gender?: string | null;
  age?: number | null;
}

export interface UpdatePatientInput {
  name: string;
}

export interface UpdatePatientDemographicsInput {
  gender?: string | null;
  age?: number | null;
}

export interface DeletePatientResult {
  patient_id: string;
  deleted: boolean;
  tasks_deleted: boolean;
  deleted_task_count: number;
}

interface PatientListResponse {
  patients: PatientSummary[];
}

export function createPatient(input: CreatePatientInput) {
  return apiRequest<PatientRecord>('/api/patients', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input)
  });
}

export async function getPatients(query?: string) {
  const params = new URLSearchParams();
  if (query && query.trim()) {
    params.set('query', query);
  }
  const path = params.toString() ? `/api/patients?${params.toString()}` : '/api/patients';
  const data = await apiRequest<PatientListResponse>(path);
  return data.patients;
}

export function getPatientDetail(patientId: string) {
  return apiRequest<PatientRecord>(`/api/patients/${encodeURIComponent(patientId)}`);
}

export function getPatientRecords(patientId: string) {
  return apiRequest<PatientDetailResponse>(`/api/patients/${encodeURIComponent(patientId)}/records`);
}

export function updatePatient(patientId: string, patch: UpdatePatientInput) {
  return apiRequest<PatientRecord>(`/api/patients/${encodeURIComponent(patientId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch)
  });
}

export function updatePatientDemographics(patientId: string, patch: UpdatePatientDemographicsInput) {
  return apiRequest<PatientRecord>(`/api/patients/${encodeURIComponent(patientId)}/demographics`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch)
  });
}

export function deletePatient(patientId: string, deleteTasks: boolean) {
  const params = new URLSearchParams({ delete_tasks: deleteTasks ? 'true' : 'false' });
  return apiRequest<DeletePatientResult>(
    `/api/patients/${encodeURIComponent(patientId)}?${params.toString()}`,
    { method: 'DELETE' }
  );
}
