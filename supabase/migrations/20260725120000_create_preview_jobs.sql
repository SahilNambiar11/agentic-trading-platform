begin;

create type public.preview_job_status as enum ('queued', 'running', 'completed', 'failed');
create type public.preview_job_stage as enum ('queued', 'parsing', 'validating', 'compiling', 'loading_data', 'backtesting', 'generating_results', 'completed', 'failed');

create table public.preview_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  status public.preview_job_status not null default 'queued',
  stage public.preview_job_stage not null default 'queued',
  progress integer not null default 5
    constraint preview_jobs_progress_check check (progress between 0 and 100),
  strategy_text text not null
    constraint preview_jobs_strategy_text_check check (char_length(strategy_text) > 0),
  strategy_name text,
  error_message text,
  preview_result jsonb,
  attempt_count integer not null default 0
    constraint preview_jobs_attempt_count_check check (attempt_count >= 0),
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  expires_at timestamptz not null
);

create index preview_jobs_user_id_idx on public.preview_jobs(user_id);
create index preview_jobs_expires_at_idx on public.preview_jobs(expires_at);
alter table public.preview_jobs enable row level security;
grant select, insert, update, delete on public.preview_jobs to authenticated;
create policy preview_jobs_owner_access on public.preview_jobs for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
commit;
