// 由 tools/export_contracts.py 从后端 OpenAPI 生成，不要手改。

export interface ApiErrorDetail {
  code: string;
}

export interface ApiErrorResponse {
  detail: ApiErrorDetail;
}

export interface ArtifactSummary {
  artifact_id: string;
  media_type: string;
  sha256: string;
  storage_key: string;
}

export interface ControlSummary {
  entity_id: string;
  parameter: string;
  label: string;
  unit: string;
  min: number;
  max: number;
  initial: number | null;
}

export interface CreateJobRequest {
  experiment_id: string;
  base_revision: string;
  prompt: string;
}

export interface ExperimentCreated {
  experiment_id: string;
  base_revision: string;
  template_id: string;
}

export interface ExperimentDetail {
  experiment_id: string;
  template_id: string;
  head_revision: string | null;
  revision_count: number;
  revisions: string[];
}

export interface HTTPValidationError {
  detail?: ValidationError[];
}

export interface JobAccepted {
  job_id: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
}

export interface JobCancelled {
  job_id: string;
  status: "cancelled";
}

export interface JobEvent {
  sequence: number;
  stage: string | null;
  event_type: string;
}

export interface JobView {
  job_id: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  stage: string | null;
  error_code: string | null;
  candidate_revision_id: string | null;
  events: JobEvent[];
}

export interface OfflineVerification {
  revision_id: string;
  verified: boolean;
  detail: Record<string, unknown>;
}

export interface RevisionArtifacts {
  revision_id: string;
  artifacts: ArtifactSummary[];
}

export interface RevisionList {
  revisions: RevisionSummary[];
}

export interface RevisionSummary {
  revision_id: string;
  parent_id: string | null;
  engine_id: string;
  created_at: string;
}

export interface RevisionViews {
  revision_id: string;
  views: Record<string, unknown>;
}

export interface RollbackRequest {
  target_revision_id: string;
}

export interface TemplateList {
  templates: TemplateSummary[];
}

export interface TemplateSummary {
  template_id: string;
  title: string;
  engine_id: "ray_optics" | "myphysicslab" | "circuitjs";
  units_per_unit: number;
  routes: string[];
  views: string[];
  controls: ControlSummary[];
  native_file: string;
}

export interface ValidationError {
  loc: string | number[];
  msg: string;
  type: string;
  input?: unknown;
  ctx?: Record<string, unknown>;
}

/** 接口清单：路径 -> operationId，供客户端封装用。 */
export interface ApiOperations {
  "GET /api/v1/artifacts/{artifact_id}/download": "download_api_v1_artifacts__artifact_id__download_get";
  "POST /api/v1/experiments": "create_experiment_api_v1_experiments_post";
  "GET /api/v1/experiments/{experiment_id}": "get_experiment_api_v1_experiments__experiment_id__get";
  "GET /api/v1/experiments/{experiment_id}/revisions": "revisions_api_v1_experiments__experiment_id__revisions_get";
  "POST /api/v1/experiments/{experiment_id}/rollback": "rollback_experiment_api_v1_experiments__experiment_id__rollback_post";
  "POST /api/v1/jobs": "create_job_api_v1_jobs_post";
  "GET /api/v1/jobs/{job_id}": "get_job_api_v1_jobs__job_id__get";
  "POST /api/v1/jobs/{job_id}/cancel": "cancel_job_api_v1_jobs__job_id__cancel_post";
  "GET /api/v1/revisions/{revision_id}/artifacts": "revision_artifacts_api_v1_revisions__revision_id__artifacts_get";
  "GET /api/v1/revisions/{revision_id}/offline_verification": "revision_offline_verification_api_v1_revisions__revision_id__offline_verification_get";
  "GET /api/v1/revisions/{revision_id}/views": "revision_views_api_v1_revisions__revision_id__views_get";
  "GET /api/v1/templates": "templates_api_v1_templates_get";
}

export const OPENAPI_VERSION = "0.1.0";
