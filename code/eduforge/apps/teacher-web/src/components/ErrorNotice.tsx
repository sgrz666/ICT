import type { ReactNode } from "react";

/** 错误码 → 教师能看懂的话。没列出来的码原样显示，不假装"未知错误"就是解释。 */
const MESSAGES: Record<string, string> = {
  TEMPLATE_NOT_FOUND: "这个模板目录里读不到，换一个或让开发侧补上。",
  EXPERIMENT_NOT_FOUND: "实验不存在或已被删除。",
  JOB_NOT_FOUND: "找不到这个任务，可能已被清理。",
  IDEMPOTENCY_CONFLICT: "同一个提交键被用于不同的需求；请重新提交。",
  ALREADY_SUCCEEDED: "这个任务已经发布成功，取消不会回滚已发布的版本。",
  ARTIFACT_NOT_FOUND: "这个版本没有登记产物。",
  ARTIFACT_FILE_MISSING: "产物文件不在磁盘上：数据库有记录但字节丢了。",
  STORAGE_KEY_OUT_OF_ROOT: "产物路径越界，已拒绝读取。",
  CONTENT_HASH_MISMATCH: "产物内容与登记的哈希不符，已拒绝交付。",
  PARAMETER_NOT_REGISTERED: "要改的对象或参数不在这个模板的登记清单里。",
  VALUE_OUT_OF_RANGE: "给的值超出模板允许的量程。",
  VIEW_NOT_REGISTERED: "要显示的视图不在模板登记清单里。",
  ROUTE_NOT_SUPPORTED: "这个模板不支持该修改路径。",
  TEMPLATE_MISMATCH: "请求声明的模板与实际装载的模板不一致。",
  SINGLE_EDIT_ONLY: "一次只能改一个参数，请拆成多次提交。",
  CODE_ROUTE_NOT_EXECUTED: "代码路径尚未接通，当前只能做配置类修改。",
  VALIDATION_NOT_PASSED: "科学对照没通过，这个结果不会被发布。",
  UPSTREAM_REJECTED: "上游模拟器不接受改后的场景。",
  PROMPT_MISSING: "任务里没有教师原话，无法规划。",
  API_NOT_CONFIGURED: "业务 API 未配置（网关的 EDUFORGE_API_URL 没设）。",
  API_UNREACHABLE: "业务 API 连不上：确认它已经启动。",
};

export function explain(code: string | null | undefined): string {
  if (!code) return "";
  return MESSAGES[code] ?? `服务端返回错误码 ${code}。`;
}

export function ErrorNotice({ code, extra }: { code: string | null; extra?: string }): ReactNode | null {
  if (!code) return null;
  return (
    <div className="notice" role="alert">
      <strong>{code}</strong>
      <div>{explain(code)}</div>
      {extra ? <div className="muted">{extra}</div> : null}
    </div>
  );
}
