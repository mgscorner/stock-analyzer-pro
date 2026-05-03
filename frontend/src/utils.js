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
  const hasFundamentalsData = hasRealFundamentals(snapshot);
  const hasCurrentFundamentalsData = hasRequiredAnnualSeries(snapshot);
  const fundamentalsMissing = snapshot.fundamentals_status === 'error'
    || snapshot.fundamentals_status === 'missing';
  const fundamentalsDisplay = fundamentalsMissing
    ? 'Missing'
    : hasFundamentalsData
      ? 'N/A'
      : 'Updating...';
  const hasCoreData = hasSnapshot && hasUsablePrice && hasHistory && hasCurrentFundamentalsData;
  const hasUsablePartialData = hasSnapshot && hasUsablePrice;
  const dataStatus = hasCoreData
    ? 'OK'
    : hasUsablePartialData
      ? 'Partial'
      : snapshot.last_error
        ? 'Update Failed'
        : 'Needs Cache';

  return {
    ticker: symbol,
    name: snapshot.name || symbol,
    price: money(snapshot.price, 2),
    revenueStatus: derivedStatus(snapshot, 'revenue') || fundamentalsDisplay,
    profitStatus: derivedStatus(snapshot, 'profit') || fundamentalsDisplay,
    ownership: ownershipDisplay(snapshot.inst_ownership),
    greenCharts: snapshot.green_charts || 'No',
    perf5y: hasHistory ? percent(performanceValue(snapshot, 'perf_5y', 'close_5y', 1260)) : 'N/A',
    perf3y: hasHistory ? percent(performanceValue(snapshot, 'perf_3y', 'close_3y', 756)) : 'N/A',
    perf1y: hasHistory ? percent(performanceValue(snapshot, 'perf_1y', 'close_1y', 252)) : 'N/A',
    perf6m: hasHistory ? percent(performanceValue(snapshot, 'perf_6m', 'close_6m', 126)) : 'N/A',
    perf3m: hasHistory ? percent(performanceValue(snapshot, 'perf_3m', 'close_3m', 63)) : 'N/A',
    perf1m: hasHistory ? percent(performanceValue(snapshot, 'perf_1m', 'close_1m', 21)) : 'N/A',
    revenueYear1: annualValue(snapshot, 'revenue', targetAnnualYears(4)[0]),
    revenueYear2: annualValue(snapshot, 'revenue', targetAnnualYears(4)[1]),
    revenueYear3: annualValue(snapshot, 'revenue', targetAnnualYears(4)[2]),
    revenueYear4: annualValue(snapshot, 'revenue', targetAnnualYears(4)[3]),
    profitYear1: annualValue(snapshot, 'profit', targetAnnualYears(4)[0]),
    profitYear2: annualValue(snapshot, 'profit', targetAnnualYears(4)[1]),
    profitYear3: annualValue(snapshot, 'profit', targetAnnualYears(4)[2]),
    profitYear4: annualValue(snapshot, 'profit', targetAnnualYears(4)[3]),
    marketCap: money(snapshot.market_cap, 0),
    dataStatus,
    comment: comment || '',
  };
}

function hasRealFundamentals(snapshot) {
  return snapshot.revenue_status === 'Growth'
    || snapshot.profit_status === 'Growth'
    || Boolean(snapshot.revenue_year_1_value)
    || Boolean(snapshot.profit_year_1_value)
    || hasAnyAnnualSeries(snapshot, 'revenue')
    || hasAnyAnnualSeries(snapshot, 'profit');
}

function hasRequiredAnnualSeries(snapshot) {
  return targetAnnualYears(4).every((year) => (
    hasAnnualValueForYear(snapshot, 'revenue', year)
    && hasAnnualValueForYear(snapshot, 'profit', year)
  ));
}

function hasAnyCurrentAnnualSeries(snapshot) {
  return targetAnnualYears(4).some((year) => (
    hasAnnualValueForYear(snapshot, 'revenue', year)
    || hasAnnualValueForYear(snapshot, 'profit', year)
  ));
}

function derivedStatus(snapshot, prefix) {
  const values = [];
  for (const year of targetAnnualYears(4)) {
    const value = annualRawValue(snapshot, prefix, year);
    if (value === null || value === undefined || value === '') continue;
    values.push(Number(value));
  }
  if (!values.length) return null;
  if (values.length < 4 || values.some((value) => Number.isNaN(value))) return null;
  return values[0] > values[1] && values[1] > values[2] && values[2] > values[3]
    ? 'Growth'
    : 'Nope';
}

function ownershipDisplay(value) {
  const num = Number(value || 0);
  if (num > 0) return percent(num);
  return 'Ownership pending';
}

function compactMoney(value) {
  if (!value) return 'N/A';
  return money(Number(value) / 1000, 0);
}

export function targetAnnualYears(count = 4) {
  const latestTargetYear = new Date().getFullYear() - 1;
  return Array.from({ length: count }, (_, index) => latestTargetYear - index);
}

function annualValue(snapshot, prefix, targetYear) {
  for (let index = 1; index <= 5; index += 1) {
    if (Number(snapshot[`${prefix}_year_${index}_label`]) === Number(targetYear)) {
      return compactMoney(snapshot[`${prefix}_year_${index}_value`]);
    }
  }
  return targetYear === targetAnnualYears(4)[0] && hasAnyCurrentAnnualSeries(snapshot)
    ? 'Not published yet'
    : 'N/A';
}

function hasAnnualValueForYear(snapshot, prefix, targetYear) {
  return annualRawValue(snapshot, prefix, targetYear) !== null;
}

function annualRawValue(snapshot, prefix, targetYear) {
  for (let index = 1; index <= 5; index += 1) {
    if (Number(snapshot[`${prefix}_year_${index}_label`]) !== Number(targetYear)) continue;
    const value = snapshot[`${prefix}_year_${index}_value`];
    return value !== null && value !== undefined && value !== '' ? value : null;
  }
  return null;
}

function hasAnyAnnualSeries(snapshot, prefix) {
  for (let index = 1; index <= 5; index += 1) {
    if (snapshot[`${prefix}_year_${index}_label`] !== null
      && snapshot[`${prefix}_year_${index}_label`] !== undefined
      && snapshot[`${prefix}_year_${index}_value`] !== null
      && snapshot[`${prefix}_year_${index}_value`] !== undefined) {
      return true;
    }
  }
  return false;
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
