-- 0002：未发布候选工作态外置到数据库。
--
-- 为什么要有这张表：`ExperimentToolService._sessions` 只是进程内字典，模型改完的
-- 那份场景在进程退出时就没了；Worker 又在基线上重放一遍操作当作交付物，于是
-- 「Agent 验过的那份」和「教师下载的那份」是两个对象。候选落库之后，
-- 同一条 job 从编辑到发布自始至终指向同一行、同一个内容哈希。
--
-- job_id 作主键 = 一个任务只有一个工作态；重试落在同一行，不会长出第二个候选。
-- state_version 是乐观并发列：写操作必须带上读到的版本号，对不上就拒写。
-- validation_id / validation_hash 记录「哪一版内容被验过」：内容一变，
-- 这两个字段就清空，旧绿灯不能继续支撑构建与发布。
create table if not exists experiment_candidates (
  job_id uuid primary key references jobs(id) on delete cascade,
  candidate_id uuid not null,
  experiment_id uuid not null,
  base_revision uuid not null,
  owner_id text not null,
  template_id text not null,
  native_data jsonb not null,
  teaching_views jsonb not null default '{}'::jsonb,
  edits jsonb not null default '[]'::jsonb,
  content_hash text not null,
  state_version int not null default 0,
  status text not null default 'editing',
  validation_id uuid,
  validation_hash text,
  agent_trace jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists experiment_candidates_candidate_uq
  on experiment_candidates (candidate_id);
create index if not exists experiment_candidates_experiment_idx
  on experiment_candidates (experiment_id, base_revision);
