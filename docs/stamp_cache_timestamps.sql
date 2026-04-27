-- One-time cache timestamp backfill for already-fetched data.
-- Run this after a preload batch when the rows already contain real values.

update public.stock_snapshots
set
    price_updated_at = case
        when price is not null and price > 0 then coalesce(price_updated_at, now())
        else price_updated_at
    end,
    history_updated_at = case
        when history_data is not null and jsonb_array_length(history_data) > 0 then coalesce(history_updated_at, now())
        else history_updated_at
    end,
    fundamentals_updated_at = case
        when fundamentals_status = 'complete'
          or revenue_year_1_value is not null
          or profit_year_1_value is not null
        then coalesce(fundamentals_updated_at, now())
        else fundamentals_updated_at
    end,
    updated_at = now()
where
    price is not null
    or history_data is not null
    or fundamentals_status is not null;
