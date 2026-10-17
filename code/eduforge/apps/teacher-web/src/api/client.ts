import type {
  ApiErrorResponse,
  ExperimentCreated,
  ExperimentDetail,
  JobAccepted,
  JobView,
  RevisionArtifacts,
  RevisionList,
  RevisionNative,
  RevisionViews,
  TemplateList,
} from "@eduforge/contracts";

// 业务 DTO 全部来自后端 OpenAPI 生成的类型（§6.2）：这里只有取数与错误码转换，
// 没有一个手写的响应结构。用 `import type` 是刻意的——生成物是类型唯一出处，
// 不该在运行时引入第二个包。
export class ApiError extends Error {
  constructor(readonly status: number, readonly code: string) {
    super(`${status} ${code}`);
  }
}

const JSON_HEADERS = { "content-type": "application/json" };

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let code = "UNKNOWN";
    try {
      const body = (await res.json()) as ApiErrorResponse;
      code = body?.detail?.code ?? "UNKNOWN";
    } catch {
      /* 非 JSON 错误体：保留状态码就够定位了 */
    }
    throw new ApiError(res.status, code);
  }
  return (await res.json()) as T;
}

export const api = {
  templates: () => call<TemplateList>("/api/v1/templates"),

  createExperiment: (templateId: string) =>
    call<ExperimentCreated>(
      `/api/v1/experiments?template_id=${encodeURIComponent(templateId)}`,
      { method: "POST" }
    ),

  // 幂等键每次提交新生成：同一次点击的重发要复用同一个键，
  // 所以由调用方（PromptEditor）持有，而不是在这里随手生成。
  submitJob: (body: { experiment_id: string; base_revision: string; prompt: string }, key: string) =>
    call<JobAccepted>("/api/v1/jobs", {
      method: "POST",
      headers: { ...JSON_HEADERS, "idempotency-key": key },
      body: JSON.stringify(body),
    }),

  job: (jobId: string, signal?: AbortSignal) =>
    call<JobView>(`/api/v1/jobs/${jobId}`, { signal }),

  experiment: (experimentId: string, signal?: AbortSignal) =>
    call<ExperimentDetail>(`/api/v1/experiments/${experimentId}`, { signal }),

  revisions: (experimentId: string) =>
    call<RevisionList>(`/api/v1/experiments/${experimentId}/revisions`),

  artifacts: (revisionId: string) =>
    call<RevisionArtifacts>(`/api/v1/revisions/${revisionId}/artifacts`),

  /** §C.3：教学视图配置只能从后端读，前端不自己拼一份"看起来一样"的表。 */
  views: (revisionId: string) =>
    call<RevisionViews>(`/api/v1/revisions/${revisionId}/views`),

  /** §C.5c：未发布的种子版本通过该接口获取其真实的 native_data 实体进行预览。 */
  revisionNative: (revisionId: string) =>
    call<RevisionNative>(`/api/v1/revisions/${revisionId}/native`),

  cancelJob: (jobId: string) => call<{ job_id: string; status: string }>(`/api/v1/jobs/${jobId}/cancel`, { method: "POST" }),

  rollbackExperiment: (experimentId: string, targetRevisionId: string) =>
    call<ExperimentDetail>(`/api/v1/experiments/${experimentId}/rollback`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ target_revision_id: targetRevisionId }),
    }),

  /** 把一份场景交给预览服务，返回它的包装页路径。 */
  registerPreview: async (scene: unknown): Promise<{ id: string; path: string }> => {
    const res = await fetch("/scene", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(scene),
    });
    if (!res.ok) throw new ApiError(res.status, "PREVIEW_REGISTER_FAILED");
    return (await res.json()) as { id: string; path: string };
  },
};

export async function sha256Hex(bytes: Uint8Array<ArrayBuffer>): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map(b => b.toString(16).padStart(2, "0"))
    .join("");
}

export type VerifiedArtifact = { bytes: Uint8Array<ArrayBuffer>; sha256: string; mediaType: string };

/**
 * 下载并**自己重算**哈希。
 *
 * 只信服务端 x-content-sha256 头是假校验：那等于让被校验方出具合格证。
 * 期望值来自产物清单里登记的 sha256，三者（字节、头、清单）必须一致。
 */
export async function downloadVerified(artifactId: string, expectedSha: string): Promise<VerifiedArtifact> {
  const res = await fetch(`/api/v1/artifacts/${artifactId}/download`);
  if (!res.ok) {
    let code = "UNKNOWN";
    try {
      code = ((await res.json()) as ApiErrorResponse)?.detail?.code ?? "UNKNOWN";
    } catch { /* 字节流错误没有 JSON 体 */ }
    throw new ApiError(res.status, code);
  }
  const bytes = new Uint8Array(await res.arrayBuffer());
  const hex = await sha256Hex(bytes);
  const header = res.headers.get("x-content-sha256") ?? "";
  if (hex !== expectedSha) throw new Error(`产物哈希与登记值不符（期望 ${expectedSha.slice(0, 12)}…，实得 ${hex.slice(0, 12)}…）`);
  if (header && header !== hex) throw new Error("响应校验头与字节重算结果不一致");
  return { bytes, sha256: hex, mediaType: res.headers.get("content-type") ?? "application/octet-stream" };
}
