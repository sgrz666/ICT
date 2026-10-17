-- 0003：验证报告绑到「验的是哪一版候选」。
--
-- 旧表只有 job_id + checks + verdict：报告与候选之间没有可核对的凭据，
-- 「验证过的那份是不是发布的那份」只能靠时间顺序相信。Gate C §C.1 要求
-- 报告绑定 candidate_id + content_hash + engine_version + validation_profile，
-- 发布门禁据此核对（`experiment_candidates.validation_hash` 只是工作态侧的镜像）。
--
-- 老行不改写：新列一律可空，历史报告按历史现场理解。
alter table validation_reports add column if not exists candidate_id uuid;
alter table validation_reports add column if not exists content_hash text;
alter table validation_reports add column if not exists engine_version text;
alter table validation_reports add column if not exists profile text;

create index if not exists validation_reports_candidate_idx
  on validation_reports (candidate_id, content_hash);
