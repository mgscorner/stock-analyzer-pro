import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

type Snapshot = Record<string, unknown>;

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const { symbol: rawSymbol } = await req.json();
    const symbol = String(rawSymbol || "").trim().toUpperCase();
    if (!symbol || !/^[A-Z0-9.-]{1,12}$/.test(symbol)) {
      return json({ ok: false, error: "Invalid ticker." }, 400);
    }

    const supabaseUrl = Deno.env.get("SUPABASE_URL");
    const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
    if (!supabaseUrl || !serviceKey) {
      return json({ ok: false, error: "Function is missing Supabase service credentials." }, 500);
    }

    const supabase = createClient(supabaseUrl, serviceKey);
    const quote = await fetchQuote(symbol);
    if (!quote || !quote.price || quote.price <= 0) {
      return json({ ok: false, error: `No valid market data found for ${symbol}.` }, 404);
    }

    const hist = await fetchHistory(symbol);
    const baselines = extractBaselines(hist);
    const perf = recalcPerformance(quote.price, baselines);

    const snapshot: Snapshot = {
      symbol,
      name: quote.name || symbol,
      price: quote.price,
      market_cap: quote.marketCap || 0,
      inst_ownership: quote.instOwnership || 0,
      revenue_status: "Nope",
      profit_status: "Nope",
      green_charts: perf.greenCharts,
      perf_5y: perf.perf5y,
      perf_3y: perf.perf3y,
      perf_1y: perf.perf1y,
      perf_6m: perf.perf6m,
      perf_3m: perf.perf3m,
      close_5y: baselines.close_5y,
      close_3y: baselines.close_3y,
      close_1y: baselines.close_1y,
      close_6m: baselines.close_6m,
      close_3m: baselines.close_3m,
      history_data: hist.slice(-1500).map((point) => ({
        date: new Date(point.t * 1000).toISOString().slice(0, 10),
        close: point.c,
      })),
      price_updated_at: new Date().toISOString(),
      history_updated_at: new Date().toISOString(),
      last_error: null,
      last_error_at: null,
    };

    const { error } = await supabase
      .from("stock_snapshots")
      .upsert(snapshot, { onConflict: "symbol" });

    if (error) {
      return json({ ok: false, error: error.message }, 500);
    }

    return json({ ok: true, snapshot });
  } catch (error) {
    return json({ ok: false, error: String(error?.message || error) }, 500);
  }
});

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      ...corsHeaders,
      "Content-Type": "application/json",
    },
  });
}

async function fetchQuote(symbol: string) {
  const url = `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${encodeURIComponent(symbol)}`;
  const res = await fetch(url, {
    headers: { "User-Agent": "Mozilla/5.0" },
  });
  if (!res.ok) return null;
  const data = await res.json();
  const quote = data?.quoteResponse?.result?.[0];
  if (!quote) return null;

  return {
    name: quote.longName || quote.shortName || symbol,
    price: numberOrZero(quote.regularMarketPrice),
    marketCap: numberOrZero(quote.marketCap),
    instOwnership: 0,
  };
}

async function fetchHistory(symbol: string) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?range=6y&interval=1d`;
  const res = await fetch(url, {
    headers: { "User-Agent": "Mozilla/5.0" },
  });
  if (!res.ok) return [];
  const data = await res.json();
  const result = data?.chart?.result?.[0];
  const timestamps = result?.timestamp || [];
  const closes = result?.indicators?.quote?.[0]?.close || [];
  const points = [];
  for (let i = 0; i < timestamps.length; i += 1) {
    const close = numberOrZero(closes[i]);
    if (timestamps[i] && close > 0) {
      points.push({ t: timestamps[i], c: close });
    }
  }
  return points;
}

function extractBaselines(points: Array<{ t: number; c: number }>) {
  return {
    close_5y: closeAtOffset(points, 1260),
    close_3y: closeAtOffset(points, 756),
    close_1y: closeAtOffset(points, 252),
    close_6m: closeAtOffset(points, 126),
    close_3m: closeAtOffset(points, 63),
  };
}

function closeAtOffset(points: Array<{ t: number; c: number }>, offset: number) {
  if (points.length <= offset) return null;
  return points[points.length - offset]?.c || null;
}

function recalcPerformance(price: number, baselines: Record<string, number | null>) {
  const perf5y = pct(price, baselines.close_5y);
  const perf3y = pct(price, baselines.close_3y);
  const perf1y = pct(price, baselines.close_1y);
  const perf6m = pct(price, baselines.close_6m);
  const perf3m = pct(price, baselines.close_3m);
  return {
    perf5y,
    perf3y,
    perf1y,
    perf6m,
    perf3m,
    greenCharts: perf5y > 0 && perf1y > 0 && perf3m > 0 ? "Yes" : "No",
  };
}

function pct(price: number, baseline: number | null) {
  if (!price || !baseline || baseline <= 0) return 0;
  return ((price - baseline) / baseline) * 100;
}

function numberOrZero(value: unknown) {
  const num = Number(value || 0);
  return Number.isFinite(num) ? num : 0;
}
