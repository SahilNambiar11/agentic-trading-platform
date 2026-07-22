begin;

create type public.backtest_status as enum (
  'queued',
  'running',
  'completed',
  'failed',
  'cancelled'
);

create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  display_name text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint profiles_display_name_length_check
    check (display_name is null or char_length(display_name) between 1 and 100)
);

create table public.strategies (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid()
    references auth.users (id) on delete cascade,
  name text not null,
  source_text text not null,
  strategy_json jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint strategies_name_length_check
    check (char_length(name) between 1 and 200),
  constraint strategies_source_text_length_check
    check (char_length(source_text) > 0),
  constraint strategies_id_user_id_key unique (id, user_id)
);

create table public.backtest_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid()
    references auth.users (id) on delete cascade,
  strategy_id uuid not null,
  status public.backtest_status not null default 'queued',
  configuration jsonb not null default '{}'::jsonb,
  results jsonb,
  error_message text,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint backtest_runs_strategy_owner_fkey
    foreign key (strategy_id, user_id)
    references public.strategies (id, user_id)
    on delete cascade
);

create table public.market_data (
  symbol text not null,
  "interval" text not null,
  "timestamp" timestamptz not null,
  open_price numeric(18, 8) not null,
  high_price numeric(18, 8) not null,
  low_price numeric(18, 8) not null,
  close_price numeric(18, 8) not null,
  adjusted_close numeric(18, 8),
  volume bigint not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint market_data_pkey primary key (symbol, "interval", "timestamp"),
  constraint market_data_symbol_check
    check (
      char_length(symbol) between 1 and 20
      and symbol = upper(symbol)
    ),
  constraint market_data_interval_check check ("interval" in ('1d')),
  constraint market_data_prices_positive_check
    check (
      open_price > 0
      and high_price > 0
      and low_price > 0
      and close_price > 0
      and (adjusted_close is null or adjusted_close > 0)
    ),
  constraint market_data_price_range_check
    check (
      low_price <= open_price
      and open_price <= high_price
      and low_price <= close_price
      and close_price <= high_price
    ),
  constraint market_data_volume_check check (volume >= 0)
);

create index strategies_user_id_idx on public.strategies (user_id);

create index backtest_runs_user_id_idx on public.backtest_runs (user_id);

create index backtest_runs_strategy_id_idx on public.backtest_runs (strategy_id);

create index market_data_symbol_timestamp_idx
  on public.market_data (symbol, "timestamp");

create function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

revoke execute on function public.set_updated_at()
  from public, anon, authenticated;

create trigger profiles_set_updated_at
before update on public.profiles
for each row execute function public.set_updated_at();

create trigger strategies_set_updated_at
before update on public.strategies
for each row execute function public.set_updated_at();

create trigger backtest_runs_set_updated_at
before update on public.backtest_runs
for each row execute function public.set_updated_at();

create trigger market_data_set_updated_at
before update on public.market_data
for each row execute function public.set_updated_at();

alter table public.profiles enable row level security;
alter table public.strategies enable row level security;
alter table public.backtest_runs enable row level security;
alter table public.market_data enable row level security;

revoke all on public.profiles from anon;
revoke all on public.strategies from anon;
revoke all on public.backtest_runs from anon;
revoke all on public.market_data from anon;

grant select, insert, update, delete
  on public.profiles, public.strategies, public.backtest_runs
  to authenticated;

revoke all on public.market_data from authenticated;
grant select on public.market_data to authenticated;
grant select, insert, update, delete on public.market_data to service_role;

create policy profiles_owner_access
on public.profiles
for all
to authenticated
using ((select auth.uid()) = id)
with check ((select auth.uid()) = id);

create policy strategies_owner_access
on public.strategies
for all
to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy backtest_runs_owner_access
on public.backtest_runs
for all
to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy market_data_authenticated_read
on public.market_data
for select
to authenticated
using (true);

commit;
