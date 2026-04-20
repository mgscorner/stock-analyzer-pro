export const DEFAULT_CONFIG = {
  max_watchlists: 5,
  max_tickers_per_list: 30,
  enable_scanner: 0,
  enable_debug_output: 0,
};

export function normalizeSymbol(value) {
  return String(value || '').trim().toUpperCase();
}

export function money(value, decimals = 0) {
  const num = Number(value || 0);
  return `$${num.toLocaleString(undefined, {
    maximumFractionDigits: decimals,
    minimumFractionDigits: decimals,
  })}`;
}

export function percent(value) {
  if (value === null || value === undefined || value === '') return 'N/A';
  const num = Number(value || 0);
  return `${num.toFixed(2)}%`;
}

export function shortDate(value) {
  if (!value) return 'Never';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Never';
  return date.toLocaleString(undefined, {
    month: 'numeric',
    day: 'numeric',
    year: '2-digit',
    hour: 'numeric',
    minute: '2-digit',
  });
}

export function displayRow(symbol, comment, snapshot = {}) {
  const hasSnapshot = Boolean(snapshot && snapshot.symbol);
  const hasUsablePrice = Number(snapshot.price || 0) > 0;
  const hasHistory = snapshot.history_status === 'complete'
    || (Array.isArray(snapshot.history_data) && snapshot.history_data.length > 0);
  const hasFundamentals = snapshot.fundamentals_status === 'complete'
    || (
      !snapshot.fundamentals_status
      && Boolean(snapshot.fundamentals_updated_at)
      && hasRealFundamentals(snapshot)
    );
  const fundamentalsMissing = snapshot.fundamentals_status === 'error'
    || snapshot.fundamentals_status === 'missing';
  const fundamentalsDisplay = hasFundamentals
    ? null
    : fundamentalsMissing
      ? 'Missing'
      : 'Updating...';
  const dataStatus = snapshot.last_error
    ? 'Update Failed'
    : hasSnapshot && hasUsablePrice && hasHistory && hasFundamentals
      ? 'OK'
      : hasSnapshot && hasUsablePrice
        ? fundamentalsMissing
          ? 'Missing Fundamentals'
          : 'Updating'
        : 'Needs Cache';

  return {
    ticker: symbol,
    name: snapshot.name || symbol,
    price: money(snapshot.price, 2),
    revenueStatus: hasFundamentals ? snapshot.revenue_status || 'N/A' : fundamentalsDisplay,
    profitStatus: hasFundamentals ? snapshot.profit_status || 'N/A' : fundamentalsDisplay,
    ownership: hasFundamentals ? percent(snapshot.inst_ownership) : fundamentalsDisplay,
    greenCharts: snapshot.green_charts || 'No',
    perf5y: hasHistory ? percent(performanceValue(snapshot, 'perf_5y', 'close_5y', 1260)) : 'N/A',
    perf3y: hasHistory ? percent(performanceValue(snapshot, 'perf_3y', 'close_3y', 756)) : 'N/A',
    perf1y: hasHistory ? percent(performanceValue(snapshot, 'perf_1y', 'close_1y', 252)) : 'N/A',
    perf6m: hasHistory ? percent(performanceValue(snapshot, 'perf_6m', 'close_6m', 126)) : 'N/A',
    perf3m: hasHistory ? percent(performanceValue(snapshot, 'perf_3m', 'close_3m', 63)) : 'N/A',
    perf1m: hasHistory ? percent(performanceValue(snapshot, 'perf_1m', 'close_1m', 21)) : 'N/A',
    revenueYear1: hasFundamentals ? annualValue(snapshot, 'revenue', targetAnnualYears()[0]) : fundamentalsDisplay,
    revenueYear2: hasFundamentals ? annualValue(snapshot, 'revenue', targetAnnualYears()[1]) : fundamentalsDisplay,
    revenueYear3: hasFundamentals ? annualValue(snapshot, 'revenue', targetAnnualYears()[2]) : fundamentalsDisplay,
    revenueYear4: hasFundamentals ? annualValue(snapshot, 'revenue', targetAnnualYears()[3]) : fundamentalsDisplay,
    revenueYear5: hasFundamentals ? annualValue(snapshot, 'revenue', targetAnnualYears()[4]) : fundamentalsDisplay,
    profitYear1: hasFundamentals ? annualValue(snapshot, 'profit', targetAnnualYears()[0]) : fundamentalsDisplay,
    profitYear2: hasFundamentals ? annualValue(snapshot, 'profit', targetAnnualYears()[1]) : fundamentalsDisplay,
    profitYear3: hasFundamentals ? annualValue(snapshot, 'profit', targetAnnualYears()[2]) : fundamentalsDisplay,
    profitYear4: hasFundamentals ? annualValue(snapshot, 'profit', targetAnnualYears()[3]) : fundamentalsDisplay,
    profitYear5: hasFundamentals ? annualValue(snapshot, 'profit', targetAnnualYears()[4]) : fundamentalsDisplay,
    marketCap: money(snapshot.market_cap, 0),
    dataStatus,
    comment: comment || '',
  };
}

function hasRealFundamentals(snapshot) {
  const ownership = Number(snapshot.inst_ownership || 0);
  return ownership > 0
    || snapshot.revenue_status === 'Growth'
    || snapshot.profit_status === 'Growth'
    || Boolean(snapshot.revenue_year_1_value)
    || Boolean(snapshot.profit_year_1_value);
}

function compactMoney(value) {
  if (!value) return 'N/A';
  return money(Number(value) / 1000, 0);
}

export function targetAnnualYears(count = 5) {
  const latestTargetYear = new Date().getFullYear() - 1;
  return Array.from({ length: count }, (_, index) => latestTargetYear - index);
}

function annualValue(snapshot, prefix, targetYear) {
  for (let index = 1; index <= 5; index += 1) {
    if (Number(snapshot[`${prefix}_year_${index}_label`]) === Number(targetYear)) {
      return compactMoney(snapshot[`${prefix}_year_${index}_value`]);
    }
  }
  return targetYear === targetAnnualYears()[0] ? 'Not published yet' : 'N/A';
}

function performanceValue(snapshot, perfKey, baselineKey, tradingDaysBack) {
  if (snapshot[perfKey] !== null && snapshot[perfKey] !== undefined && snapshot[perfKey] !== '') {
    return snapshot[perfKey];
  }
  const price = Number(snapshot.price || 0);
  const baseline = Number(snapshot[baselineKey] || 0);
  if (price > 0 && baseline > 0) {
    return ((price - baseline) / baseline) * 100;
  }
  return historyPerf(snapshot, tradingDaysBack);
}

function historyPerf(snapshot, tradingDaysBack) {
  const price = Number(snapshot.price || 0);
  const history = Array.isArray(snapshot.history_data) ? snapshot.history_data : [];
  if (price <= 0 || history.length <= tradingDaysBack) return null;
  const baselineIndex = Math.max(0, history.length - 1 - tradingDaysBack);
  const baseline = Number(history[baselineIndex]?.close || 0);
  return baseline > 0 ? ((price - baseline) / baseline) * 100 : null;
}

export function sortValue(value) {
  if (value === null || value === undefined) return '';
  const text = String(value);
  const numeric = Number(text.replace(/[$,%]/g, '').replace(/,/g, ''));
  return Number.isNaN(numeric) ? text.toLowerCase() : numeric;
}

export function mergeConfig(rows = []) {
  const config = { ...DEFAULT_CONFIG };
  for (const row of rows) {
    if (!row?.key) continue;
    const numeric = Number(row.value);
    config[row.key] = Number.isNaN(numeric) ? row.value : numeric;
  }
  return config;
}
