import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { supabase, supabaseConfigured, workerApiUrl } from './supabaseClient';
import ChartPanel from './ChartPanel';
import {
  displayRow,
  mergeConfig,
  normalizeSymbol,
  shortDate,
  sortValue,
  targetAnnualYears,
} from './utils';
import './styles.css';

const annualYears = targetAnnualYears(4);
const ACTIVITY_HEARTBEAT_MS = 60 * 1000;
const FEEDBACK_PROMPT_COOLDOWN_MS = 7 * 24 * 60 * 60 * 1000;

const columns = [
  ['ticker', 'Ticker'],
  ['name', 'Name'],
  ['price', 'Price'],
  ['revenueStatus', 'Revenue'],
  ['profitStatus', 'Profit'],
  ['ownership', 'Inst. Own.'],
  ['greenCharts', 'Green Charts'],
  ['perf5y', '5Y %'],
  ['perf3y', '3Y %'],
  ['perf1y', '1Y %'],
  ['perf6m', '6M %'],
  ['perf3m', '3M %'],
  ['perf1m', '1M %'],
  ['revenueYear1', `Revenue ${annualYears[0]}`],
  ['revenueYear2', `Revenue ${annualYears[1]}`],
  ['revenueYear3', `Revenue ${annualYears[2]}`],
  ['revenueYear4', `Revenue ${annualYears[3]}`],
  ['profitYear1', `Profit ${annualYears[0]}`],
  ['profitYear2', `Profit ${annualYears[1]}`],
  ['profitYear3', `Profit ${annualYears[2]}`],
  ['profitYear4', `Profit ${annualYears[3]}`],
  ['marketCap', 'Market Cap'],
  ['dataStatus', 'Status'],
  ['comment', 'Comment'],
];

const PRICE_TTL_MS = 15 * 60 * 1000;

function App() {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [passwordRecovery, setPasswordRecovery] = useState(false);

  useEffect(() => {
    if (!supabaseConfigured) {
      setLoading(false);
      return;
    }

    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });

    const { data: listener } = supabase.auth.onAuthStateChange((event, nextSession) => {
      setSession(nextSession);
      if (event === 'PASSWORD_RECOVERY') {
        setPasswordRecovery(true);
      }
    });

    return () => listener.subscription.unsubscribe();
  }, []);

  if (!supabaseConfigured) {
    return <MissingConfig />;
  }

  if (loading) {
    return <main className="center-panel">Loading...</main>;
  }

  if (!session) {
    return <AuthScreen />;
  }

  if (passwordRecovery) {
    return <PasswordResetScreen onComplete={() => setPasswordRecovery(false)} />;
  }

  return <Dashboard session={session} />;
}

function MissingConfig() {
  return (
    <main className="center-panel">
      <h1>Stock Analyzer Pro</h1>
      <p>Missing Supabase environment variables.</p>
      <code>VITE_SUPABASE_URL</code>
      <code>VITE_SUPABASE_ANON_KEY</code>
    </main>
  );
}

function AuthScreen() {
  const [mode, setMode] = useState('sign-in');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');

  async function submit(event) {
    event.preventDefault();
    setMessage('');

    if (mode === 'reset') {
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: window.location.origin,
      });
      setMessage(error ? error.message : 'Password reset email sent.');
      return;
    }

    const action =
      mode === 'sign-in'
        ? supabase.auth.signInWithPassword({ email, password })
        : supabase.auth.signUp({ email, password });

    const { error } = await action;
    if (error) {
      setMessage(error.message);
    } else if (mode === 'sign-up') {
      setMessage('Account created. Confirm your email if required, then sign in.');
    }
  }

  return (
    <main className="auth-shell">
      <form className="auth-card" onSubmit={submit}>
        <h1>Stock Analyzer Pro</h1>
        <p>Sign in to manage your watchlists.</p>
        <div className="segmented">
          <button type="button" className={mode === 'sign-in' ? 'active' : ''} onClick={() => setMode('sign-in')}>
            Sign In
          </button>
          <button type="button" className={mode === 'sign-up' ? 'active' : ''} onClick={() => setMode('sign-up')}>
            Create Account
          </button>
        </div>
        <label>
          Email
          <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" required />
        </label>
        <label>
          Password
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            required={mode !== 'reset'}
            disabled={mode === 'reset'}
          />
        </label>
        <button className="primary" type="submit">
          {mode === 'reset' ? 'Send Reset Email' : mode === 'sign-in' ? 'Sign In' : 'Create Account'}
        </button>
        <button
          className="ghost auth-link"
          type="button"
          onClick={() => {
            setMessage('');
            setMode(mode === 'reset' ? 'sign-in' : 'reset');
          }}
        >
          {mode === 'reset' ? 'Back to Sign In' : 'Forgot Password'}
        </button>
        {message && <p className="notice">{message}</p>}
      </form>
    </main>
  );
}

function PasswordResetScreen({ onComplete }) {
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [message, setMessage] = useState('');

  async function submit(event) {
    event.preventDefault();
    setMessage('');
    if (password.length < 8) {
      setMessage('Use at least 8 characters.');
      return;
    }
    if (password !== confirmPassword) {
      setMessage('Passwords do not match.');
      return;
    }
    const { error } = await supabase.auth.updateUser({ password });
    if (error) {
      setMessage(error.message);
      return;
    }
    onComplete();
  }

  return (
    <main className="auth-shell">
      <form className="auth-card" onSubmit={submit}>
        <h1>Set New Password</h1>
        <label>
          New Password
          <input value={password} onChange={(event) => setPassword(event.target.value)} type="password" required />
        </label>
        <label>
          Confirm Password
          <input value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} type="password" required />
        </label>
        <button className="primary" type="submit">Update Password</button>
        {message && <p className="notice">{message}</p>}
      </form>
    </main>
  );
}

function Dashboard({ session }) {
  const user = session.user;
  const [config, setConfig] = useState({});
  const [watchlists, setWatchlists] = useState([]);
  const [activeList, setActiveList] = useState('');
  const [watchlistData, setWatchlistData] = useState({});
  const [snapshots, setSnapshots] = useState({});
  const [newTicker, setNewTicker] = useState('');
  const [newListName, setNewListName] = useState('');
  const [manageTicker, setManageTicker] = useState('');
  const [manageComment, setManageComment] = useState('');
  const [pendingDeleteList, setPendingDeleteList] = useState(false);
  const [message, setMessageState] = useState('');
  const [messageType, setMessageType] = useState('info');
  const [refreshJob, setRefreshJob] = useState(null);
  const [manualWaitJobId, setManualWaitJobId] = useState('');
  const [sortConfig, setSortConfig] = useState({ key: 'ticker', direction: 'asc' });
  const [hiddenColumns, setHiddenColumns] = useState(() => loadHiddenColumns(user.id));
  const [chartTicker, setChartTicker] = useState('');
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackType, setFeedbackType] = useState('general');
  const [feedbackMessage, setFeedbackMessage] = useState('');
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const [showFeedbackPrompt, setShowFeedbackPrompt] = useState(false);
  const [sidebarAlerts, setSidebarAlerts] = useState([]);
  const [alertEvents, setAlertEvents] = useState([]);
  const [focusedAlertId, setFocusedAlertId] = useState('');
  const [sidebarFolds, setSidebarFolds] = useState(() => loadSidebarFolds(user.id));
  const autoPriceRefreshRef = useRef('');
  const pendingInitialSymbolsRef = useRef(new Set());

  useEffect(() => {
    loadConfig();
    loadWatchlists();
    loadAlertSidebar();
    setShowFeedbackPrompt(true);
  }, []);

  useEffect(() => {
    if (activeList) loadWatchlistData(activeList);
  }, [activeList]);

  useEffect(() => {
    const symbols = Object.keys(watchlistData);
    if (symbols.length) {
      loadSnapshots(symbols).then((loadedSnapshots) => {
        maybeRefreshVisibleData(symbols, loadedSnapshots || {}, 'visible_data_initial');
      });
      if (manageTicker && !symbols.includes(manageTicker)) setManageTicker('');
      if (chartTicker && !symbols.includes(chartTicker)) setChartTicker('');
    } else {
      setSnapshots({});
      setManageTicker('');
      setManageComment('');
      setChartTicker('');
    }
  }, [watchlistData]);

  useEffect(() => {
    const symbols = Object.keys(watchlistData);
    if (!symbols.length) return undefined;

    const timer = window.setInterval(() => {
      maybeRefreshVisibleData(symbols, snapshots, 'visible_data_scheduled');
    }, PRICE_TTL_MS);

    return () => window.clearInterval(timer);
  }, [watchlistData, snapshots]);

  useEffect(() => {
    if (!watchlists.length || !activeList) return undefined;
    reportWatchlistActivity();
    const timer = window.setInterval(() => {
      reportWatchlistActivity();
    }, ACTIVITY_HEARTBEAT_MS);
    return () => window.clearInterval(timer);
  }, [watchlists, activeList]);

  useEffect(() => {
    if (chartTicker && watchlistData[chartTicker] !== undefined && chartTicker !== manageTicker) {
      setManageTicker(chartTicker);
      return;
    }
    if (manageTicker) {
      setManageComment(watchlistData[manageTicker] || '');
    } else {
      setManageComment('');
    }
  }, [manageTicker, chartTicker, watchlistData]);

  useEffect(() => {
    window.localStorage.setItem(hiddenColumnsKey(user.id), JSON.stringify(hiddenColumns));
  }, [hiddenColumns, user.id]);

  useEffect(() => {
    window.localStorage.setItem(sidebarFoldsKey(user.id), JSON.stringify(sidebarFolds));
  }, [sidebarFolds, user.id]);

  useEffect(() => {
    if (!message) return undefined;
    const timer = window.setTimeout(() => {
      setMessageState('');
      setMessageType('info');
    }, messageType === 'error' ? 7000 : 4500);
    return () => window.clearTimeout(timer);
  }, [message, messageType]);

  useEffect(() => {
    const reload = () => {
      loadAlertSidebar();
    };
    window.addEventListener('alerts-changed', reload);
    const timer = window.setInterval(reload, 60000);
    return () => {
      window.removeEventListener('alerts-changed', reload);
      window.clearInterval(timer);
    };
  }, [user.id]);

  useEffect(() => {
    if (!refreshJob?.id) return undefined;
    if (refreshJob.id === manualWaitJobId) return undefined;

    let stopped = false;
    const timer = window.setInterval(async () => {
      const job = await loadRefreshJob(refreshJob.id);
      if (stopped || !job) return;

      setRefreshJob(job);
      await loadSnapshots(Object.keys(watchlistData));
      if (['done', 'failed', 'partial'].includes(job.status)) {
        for (const symbol of job.symbols || []) {
          pendingInitialSymbolsRef.current.delete(normalizeSymbol(symbol));
        }
        window.clearInterval(timer);
        setMessage(jobMessage(job));
      }
    }, 1000);

    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [refreshJob?.id, manualWaitJobId, watchlistData]);

  async function loadConfig() {
    const { data } = await supabase.from('app_config').select('key,value');
    setConfig(mergeConfig(data || []));
  }

  function setMessage(nextMessage, type = 'info') {
    setMessageState(nextMessage);
    setMessageType(type);
  }

  async function loadWatchlists() {
    const { data, error } = await supabase
      .from('watchlists')
      .select('watchlist_name')
      .eq('user_id', user.id);

    if (error) {
      setMessage(error.message, 'error');
      return;
    }

    const names = [...new Set((data || []).map((row) => row.watchlist_name).filter(Boolean))].sort();
    setWatchlists(names);
    const savedList = window.localStorage.getItem(lastActiveListKey(user.id));
    setActiveList((current) => current || (names.includes(savedList) ? savedList : names[0] || ''));
  }

  async function loadWatchlistData(name) {
    const { data, error } = await supabase
      .from('watchlists')
      .select('*')
      .eq('user_id', user.id)
      .eq('watchlist_name', name);

    if (error) {
      setMessage(error.message, 'error');
      return;
    }

    const next = {};
    for (const row of data || []) {
      next[normalizeSymbol(row.ticker_symbol)] = row.comment || '';
    }
    window.localStorage.setItem(lastActiveListKey(user.id), name);
    setWatchlistData(next);
    setPendingDeleteList(false);
  }

  async function loadSnapshots(symbols) {
    const { data, error } = await supabase
      .from('stock_snapshots')
      .select('*')
      .in('symbol', symbols);

    if (error) {
      setMessage(error.message, 'error');
      return;
    }

    const next = {};
    for (const row of data || []) {
      next[normalizeSymbol(row.symbol)] = row;
    }
    setSnapshots(next);
    return next;
  }

  async function loadAlertSidebar() {
    const [{ data: alertsData, error: alertsError }, { data: eventsData, error: eventsError }] = await Promise.all([
      supabase
        .from('alerts')
        .select('id,symbol,condition_type,threshold,active,last_triggered_at')
        .eq('user_id', user.id)
        .order('active', { ascending: false })
        .order('created_at', { ascending: false }),
      supabase
        .from('alert_events')
        .select('id,alert_id,symbol,trigger_price,bar_time,created_at')
        .eq('user_id', user.id)
        .order('created_at', { ascending: false })
        .limit(12),
    ]);

    if (alertsError) {
      console.warn('alert sidebar load failed', alertsError.message);
    } else {
      setSidebarAlerts(alertsData || []);
    }

    if (eventsError) {
      console.warn('alert events load failed', eventsError.message);
    } else {
      setAlertEvents(eventsData || []);
    }
  }

  async function goToAlertSymbol(rawSymbol, alertId = '') {
    const symbol = normalizeSymbol(rawSymbol);
    if (!symbol) return;
    if (watchlistData[symbol] !== undefined) {
      setChartTicker(symbol);
      setFocusedAlertId(alertId);
      return;
    }
    const { data, error } = await supabase
      .from('watchlists')
      .select('watchlist_name')
      .eq('user_id', user.id)
      .eq('ticker_symbol', symbol)
      .limit(1);
    if (error) {
      setMessage(error.message, 'error');
      return;
    }
    const targetList = data?.[0]?.watchlist_name;
    if (targetList) {
      setActiveList(targetList);
      setChartTicker(symbol);
      setFocusedAlertId(alertId);
      return;
    }
    setMessage(`${symbol} is not in your watchlists.`, 'error');
  }

  async function maybeRefreshVisibleData(symbols, snapshotMap, mode) {
    const dueSymbols = symbols.filter((symbol) => !pendingInitialSymbolsRef.current.has(symbol));
    if (!dueSymbols.length) return;
    const bucket = Math.floor(Date.now() / PRICE_TTL_MS);
    const signature = `${activeList}|${mode}|${bucket}|${dueSymbols.sort().join(',')}`;
    if (autoPriceRefreshRef.current === signature) return;
    autoPriceRefreshRef.current = signature;

    try {
      await requestRefresh(dueSymbols, activeList, { mode: 'smart_visible', layers: [], quiet: true });
    } catch (error) {
      setMessage(`Refresh could not start: ${error.message}`, 'error');
    }
  }

  async function requestRefresh(symbols, watchlistName = activeList, options = {}) {
    if (!workerApiUrl) {
      setMessage('Missing VITE_WORKER_API_URL. Start the Python worker and set the frontend env var.', 'error');
      return null;
    }

    const cleanSymbols = [...new Set((symbols || []).map(normalizeSymbol).filter(Boolean))];
    if (!cleanSymbols.length) return null;
    const accessToken = await currentAccessToken();

    const response = await fetch(`${workerApiUrl}/refresh`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        symbols: cleanSymbols,
        watchlist_name: watchlistName || null,
        mode: options.mode || 'visible_quote',
        layers: options.layers || [],
      }),
    });

    const body = await response.json().catch(() => ({}));
    if (!response.ok || !body.ok) {
      throw new Error(body.detail || body.error || 'Refresh request failed.');
    }

    const job = { id: body.job_id, status: body.status, symbols: body.symbols };
    setRefreshJob(body.status === 'done' ? null : job);
    if (!options.quiet) {
      setMessage(body.message || `Refreshing ${cleanSymbols.join(', ')}...`);
    }
    return job;
  }

  async function reportWatchlistActivity() {
    if (!workerApiUrl || !watchlists.length || !activeList) return;
    const accessToken = await currentAccessToken();
    const response = await fetch(`${workerApiUrl}/activity`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        watchlists,
        active_watchlist: activeList,
      }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      console.warn('watchlist activity update failed', body.detail || body.error || response.status);
    }
  }

  async function loadRefreshJob(jobId) {
    if (!workerApiUrl) return null;
    const accessToken = await currentAccessToken();
    const response = await fetch(`${workerApiUrl}/jobs/${jobId}`, {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok || !body.ok) {
      setMessage(body.detail || body.error || 'Could not load refresh job.', 'error');
      return null;
    }
    return body.job;
  }

  async function currentAccessToken() {
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token || session.access_token;
  }

  async function waitForJob(jobId, timeoutMs = 60000) {
    const started = Date.now();
    setManualWaitJobId(jobId);
    while (Date.now() - started < timeoutMs) {
      await sleep(1000);
      const job = await loadRefreshJob(jobId);
      if (!job) return null;
      setRefreshJob(job);
      if (['done', 'failed', 'partial'].includes(job.status)) {
        setManualWaitJobId('');
        return job;
      }
    }
    setManualWaitJobId('');
    return null;
  }

  async function refreshCurrentWatchlist() {
    const symbols = Object.keys(watchlistData);
    if (!symbols.length) return;
    try {
      await requestRefresh(symbols, activeList, { mode: 'smart_visible', layers: [] });
    } catch (error) {
      setMessage(error.message, 'error');
    }
  }

  async function createWatchlist() {
    const cleanName = newListName.trim();
    if (!cleanName) return;
    if (watchlists.includes(cleanName)) {
      setMessage('A watchlist with this name already exists.', 'error');
      return;
    }
    if (watchlists.length >= Number(config.max_watchlists || 5)) {
      setMessage(`Basic plan limit: ${config.max_watchlists} watchlists.`, 'error');
      return;
    }
    setWatchlists([...watchlists, cleanName].sort());
    setActiveList(cleanName);
    setWatchlistData({});
    setNewListName('');
    setMessage('');
  }

  function snapshotReadyForAdd(snapshot) {
    return Boolean(
      snapshot
      && Number(snapshot.price || 0) > 0
      && snapshot.quote_status === 'complete'
      && snapshot.history_status === 'complete'
      && snapshot.fundamentals_status === 'complete'
      && Number(snapshot.inst_ownership || 0) > 0
    );
  }

  async function addTicker(event) {
    event.preventDefault();
    const symbol = normalizeSymbol(newTicker);
    if (!activeList || !symbol) return;

    if (watchlistData[symbol] !== undefined) {
      setNewTicker('');
      setMessage(`${symbol} is already in ${activeList}.`, 'error');
      return;
    }

    if (Object.keys(watchlistData).length >= Number(config.max_tickers_per_list || 30)) {
      setMessage(`Basic plan limit: ${config.max_tickers_per_list} tickers per list.`, 'error');
      return;
    }

    const { data: existingSnapshot, error: snapshotError } = await supabase
      .from('stock_snapshots')
      .select('symbol,price,name,quote_status,history_status,fundamentals_status,inst_ownership')
      .eq('symbol', symbol)
      .maybeSingle();

    if (snapshotError) {
      setMessage(snapshotError.message, 'error');
      return;
    }

    const nextWatchlistData = { ...watchlistData, [symbol]: '' };
    pendingInitialSymbolsRef.current.add(symbol);

    try {
      setMessage(snapshotReadyForAdd(existingSnapshot) ? `Using cached data for ${symbol}...` : `Checking ${symbol}...`);
      const job = await requestRefresh([symbol], activeList, {
        mode: 'initial',
        layers: ['quote', 'history', 'fundamentals'],
        quiet: true,
      });
      const finishedJob = job?.id ? await waitForJob(job.id, 45000) : null;
      if (!finishedJob || finishedJob.status !== 'done') {
        throw new Error(finishedJob?.error || 'Ticker validation failed.');
      }
      const { data: validatedSnapshot, error: validateError } = await supabase
        .from('stock_snapshots')
        .select('symbol,price,name,quote_status,history_status,fundamentals_status,inst_ownership')
        .eq('symbol', symbol)
        .maybeSingle();
      if (validateError) throw validateError;
      if (!snapshotReadyForAdd(validatedSnapshot)) {
        throw new Error(`Could not fully fetch ${symbol}. Try again later.`);
      }
      setMessage(`Found ${validatedSnapshot.name || symbol}. Adding ${symbol}...`);
    } catch (error) {
      pendingInitialSymbolsRef.current.delete(symbol);
      setMessage(`Could not add ${symbol}: ${error.message}`, 'error');
      return;
    }

    const { error } = await supabase.from('watchlists').insert({
      user_id: user.id,
      ticker_symbol: symbol,
      comment: '',
      watchlist_name: activeList,
    });

    if (error) {
      pendingInitialSymbolsRef.current.delete(symbol);
      setMessage(error.message, 'error');
      return;
    }

    setWatchlistData(nextWatchlistData);
    const loadedSnapshots = await loadSnapshots(Object.keys(nextWatchlistData));
    pendingInitialSymbolsRef.current.delete(symbol);
    setChartTicker(symbol);
    setNewTicker('');
    const addedName = loadedSnapshots?.[symbol]?.name || symbol;
    setMessage(`Added ${symbol}${addedName !== symbol ? ` - ${addedName}` : ''}.`);
  }

  async function saveComment(event) {
    event.preventDefault();
    if (!activeList || !manageTicker) return;

    const { error } = await supabase
      .from('watchlists')
      .update({ comment: manageComment })
      .eq('user_id', user.id)
      .eq('watchlist_name', activeList)
      .eq('ticker_symbol', manageTicker);

    if (error) {
      setMessage(error.message, 'error');
      return;
    }

    setWatchlistData({ ...watchlistData, [manageTicker]: manageComment });
    setMessage('Comment saved.');
  }

  async function deleteTicker() {
    if (!activeList || !manageTicker) return;
    const { error } = await supabase
      .from('watchlists')
      .delete()
      .eq('user_id', user.id)
      .eq('watchlist_name', activeList)
      .eq('ticker_symbol', manageTicker);

    if (error) {
      setMessage(error.message, 'error');
      return;
    }

    const next = { ...watchlistData };
    delete next[manageTicker];
    setWatchlistData(next);
    setMessage('');
  }

  async function deleteCurrentWatchlist() {
    if (!activeList) return;
    const { error } = await supabase
      .from('watchlists')
      .delete()
      .eq('user_id', user.id)
      .eq('watchlist_name', activeList);

    if (error) {
      setMessage(error.message, 'error');
      return;
    }

    const remaining = watchlists.filter((name) => name !== activeList);
    setWatchlists(remaining);
    setActiveList(remaining[0] || '');
    setWatchlistData({});
    setPendingDeleteList(false);
  }

  async function submitFeedback(event) {
    event.preventDefault();
    const messageText = feedbackMessage.trim();
    if (!messageText) {
      setMessage('Write a short message first.', 'error');
      return;
    }
    setFeedbackSubmitting(true);
    const payload = {
      user_id: user.id,
      feedback_type: feedbackType,
      message: messageText,
      context_watchlist: activeList || null,
      context_symbol: chartTicker || null,
    };
    const { error } = await supabase.from('user_feedback').insert(payload);
    setFeedbackSubmitting(false);
    if (error) {
      setMessage(error.message, 'error');
      return;
    }
    dismissFeedbackPrompt(user.id);
    setShowFeedbackPrompt(false);
    setFeedbackOpen(false);
    setFeedbackType('general');
    setFeedbackMessage('');
    setMessage('Feedback sent.');
  }

  function openFeedback(type = 'general') {
    setFeedbackType(type);
    setFeedbackOpen(true);
  }

  const rows = useMemo(() => {
    const unsorted = Object.entries(watchlistData).map(([symbol, comment]) =>
      displayRow(symbol, comment, snapshots[symbol])
    );
    return [...unsorted].sort((a, b) => {
      const left = sortValue(a[sortConfig.key]);
      const right = sortValue(b[sortConfig.key]);
      if (left < right) return sortConfig.direction === 'asc' ? -1 : 1;
      if (left > right) return sortConfig.direction === 'asc' ? 1 : -1;
      return 0;
    });
  }, [watchlistData, snapshots, sortConfig]);

  const lastPriceUpdate = latestDate(Object.values(snapshots), 'price_updated_at');
  const staleCount = rows.filter((row) => row.dataStatus !== 'OK').length;
  const visibleColumns = columns.filter(([key]) => !hiddenColumns.includes(key));
  const sortedWatchlistSymbols = Object.keys(watchlistData).sort();
  const activeRefreshText = refreshJob && ['queued', 'running'].includes(refreshJob.status)
    ? `Refresh job ${refreshJob.status}: ${(refreshJob.symbols || []).join(', ')}`
    : '';
  const statusText = activeRefreshText || message || 'Ready.';
  const statusType = activeRefreshText ? 'info' : message ? messageType : 'idle';
  const unreadAlertCount = countUnreadAlertEvents(user.id, alertEvents);

  function toggleColumn(key) {
    if (key === 'ticker') return;
    setHiddenColumns((current) => (
      current.includes(key)
        ? current.filter((item) => item !== key)
        : [...current, key]
    ));
  }

  function resetColumns() {
    setHiddenColumns([]);
  }

  function setSidebarFold(key, open) {
    setSidebarFolds((current) => ({ ...current, [key]: open }));
  }

  function exportVisibleCsv() {
    const header = visibleColumns.map(([, label]) => label);
    const body = rows.map((row) => visibleColumns.map(([key]) => row[key] ?? ''));
    const csv = [header, ...body].map((line) => line.map(csvCell).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${activeList || 'watchlist'}-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <strong>{user.email}</strong>
          <button className="ghost" onClick={() => supabase.auth.signOut()}>
            Log Out
          </button>
        </div>

        <section>
          <details className="column-panel" open={sidebarFolds.watchlists} onToggle={(event) => setSidebarFold('watchlists', event.currentTarget.open)}>
            <summary>Manage Watchlists</summary>
          <select value={activeList} onChange={(event) => setActiveList(event.target.value)}>
            {watchlists.map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
          {activeList && !pendingDeleteList && (
            <button className="danger ghost full-width watchlist-delete" onClick={() => setPendingDeleteList(true)}>
              Delete Current Watchlist
            </button>
          )}
          {pendingDeleteList && (
            <div className="confirm-box">
              <p>Delete {activeList}?</p>
              <button className="danger" onClick={deleteCurrentWatchlist}>Confirm</button>
              <button onClick={() => setPendingDeleteList(false)}>Cancel</button>
            </div>
          )}
          <div className="inline-form">
            <input
              value={newListName}
              onChange={(event) => setNewListName(event.target.value)}
              placeholder="New list"
            />
            <button onClick={createWatchlist}>Create</button>
          </div>
          </details>
        </section>

        <section>
          <details className="column-panel" open={sidebarFolds.tickers} onToggle={(event) => setSidebarFold('tickers', event.currentTarget.open)}>
            <summary>Manage Tickers</summary>
            <h2>Add Ticker</h2>
            <form className="inline-form" onSubmit={addTicker}>
              <input value={newTicker} onChange={(event) => setNewTicker(event.target.value)} placeholder="Ticker" />
              <button type="submit">Add</button>
            </form>

            {!!Object.keys(watchlistData).length && (
              <>
                <h2>Manage Ticker</h2>
                <input
                  value={manageTicker || ''}
                  placeholder="Select a row in the table or chart ticker first."
                  readOnly
                />
                <form onSubmit={saveComment}>
                  <textarea value={manageComment} onChange={(event) => setManageComment(event.target.value)} placeholder="Add a note..." />
                  <button type="submit" disabled={!manageTicker}>Save Comment</button>
                  <button type="button" className="danger ghost" disabled={!manageTicker} onClick={deleteTicker}>Delete Ticker</button>
                </form>
              </>
            )}
          </details>
        </section>

        {Number(config.enable_debug_output) === 1 && (
          <section>
            <h2>System</h2>
            <p>Max lists: {config.max_watchlists}</p>
            <p>Max tickers: {config.max_tickers_per_list}</p>
          </section>
        )}

        <section>
          <details className="column-panel" open={sidebarFolds.alerts} onToggle={(event) => setSidebarFold('alerts', event.currentTarget.open)}>
            <summary>
              Manage Alerts
              {unreadAlertCount ? <span className="sidebar-badge">{unreadAlertCount}</span> : null}
            </summary>
          <button
            className="ghost full-width"
            disabled={!alertEvents.length}
            onClick={() => {
              markAlertEventsSeen(user.id, alertEvents);
              setAlertEvents([...alertEvents]);
            }}
          >
            Mark Triggered Seen
          </button>
          <div className="alert-sidebar-group">
            <strong>Active</strong>
            {sidebarAlerts.filter((alert) => alert.active).length ? (
              sidebarAlerts
                .filter((alert) => alert.active)
                .slice(0, 8)
                .map((alert) => (
                  <div key={alert.id} className="alert-sidebar-row">
                    <button className="ghost alert-symbol-button" onClick={() => goToAlertSymbol(alert.symbol, alert.id)}>
                      {alert.symbol}
                    </button>
                    <span>{alert.condition_type === 'price_below' ? 'Below' : 'Above'} {formatAlertPrice(alert.threshold)}</span>
                  </div>
                ))
            ) : (
              <p className="sidebar-empty">No active alerts.</p>
            )}
          </div>
          <div className="alert-sidebar-group">
            <strong>Triggered</strong>
            {alertEvents.length ? (
              alertEvents.slice(0, 8).map((event) => (
                <div key={event.id} className={`alert-sidebar-row ${isAlertEventUnread(user.id, event) ? 'unread' : ''}`}>
                  <button className="ghost alert-symbol-button" onClick={() => goToAlertSymbol(event.symbol, event.alert_id)}>
                    {event.symbol}
                  </button>
                  <span>{formatAlertPrice(event.trigger_price)} {shortDate(event.created_at)}</span>
                </div>
              ))
            ) : (
              <p className="sidebar-empty">No triggered alerts yet.</p>
            )}
          </div>
          </details>
        </section>

        <section>
          <details className="column-panel" open={sidebarFolds.columns} onToggle={(event) => setSidebarFold('columns', event.currentTarget.open)}>
            <summary>Manage Columns</summary>
          <div className="column-list">
            {columns.map(([key, label]) => (
              <label key={key} className="column-toggle">
                <input
                  type="checkbox"
                  checked={!hiddenColumns.includes(key)}
                  disabled={key === 'ticker'}
                  onChange={() => toggleColumn(key)}
                />
                {label}
              </label>
            ))}
          </div>
          <button className="ghost" onClick={resetColumns}>Show All Columns</button>
          </details>
        </section>
      </aside>

      <main className="content">
        <div className="topbar">
          <div>
            <h1>{activeList || 'Stock Analyzer Pro'}</h1>
            <p>{staleCount ? `${staleCount} rows need attention` : 'Data current'} | Price {shortDate(lastPriceUpdate)}</p>
          </div>
          <div className="topbar-actions">
            <button className="ghost" onClick={exportVisibleCsv} disabled={!rows.length}>Export CSV</button>
            <button onClick={refreshCurrentWatchlist} disabled={refreshJob && ['queued', 'running'].includes(refreshJob.status)}>
              {refreshJob && ['queued', 'running'].includes(refreshJob.status) ? 'Refreshing...' : 'Refresh'}
            </button>
          </div>
        </div>

        <div className={`status-line ${statusType}`}>{statusText}</div>

        {showFeedbackPrompt && !feedbackOpen && (
          <div className="soft-prompt">
            <div>
              <strong>Feedback</strong>
              <p>What is missing or slowing you down?</p>
            </div>
            <div className="soft-prompt-actions">
              <button className="ghost" onClick={() => openFeedback('feature')}>Tell Us</button>
              <button className="ghost" onClick={() => {
                dismissFeedbackPrompt(user.id);
                setShowFeedbackPrompt(false);
              }}>Dismiss</button>
            </div>
          </div>
        )}

        {!activeList ? (
          <EmptyState text="Create a watchlist to get started." />
        ) : !rows.length ? (
          <EmptyState text="Add tickers from the sidebar." />
        ) : (
          <StockTable
            rows={rows}
            columns={visibleColumns}
            sortConfig={sortConfig}
            setSortConfig={setSortConfig}
            selectedTicker={chartTicker}
            onSelectTicker={setChartTicker}
          />
        )}
        {activeList && rows.length > 0 && (
          <ChartPanel
            symbol={chartTicker}
            snapshot={snapshots[chartTicker]}
            userId={user.id}
            activeList={activeList}
            focusAlertId={focusedAlertId}
            onFocusAlertHandled={() => setFocusedAlertId('')}
          />
        )}
        {feedbackOpen && (
          <div className="modal-backdrop" onClick={() => setFeedbackOpen(false)}>
            <div className="modal-card" onClick={(event) => event.stopPropagation()}>
              <div className="modal-header">
                <h2>Feedback</h2>
                <button className="ghost" onClick={() => setFeedbackOpen(false)}>Close</button>
              </div>
              <form onSubmit={submitFeedback}>
                <label>
                  Type
                  <select value={feedbackType} onChange={(event) => setFeedbackType(event.target.value)}>
                    <option value="general">General</option>
                    <option value="feature">Feature Request</option>
                    <option value="bug">Bug</option>
                  </select>
                </label>
                <label>
                  Message
                  <textarea
                    value={feedbackMessage}
                    onChange={(event) => setFeedbackMessage(event.target.value)}
                    placeholder="What is missing or slowing you down?"
                  />
                </label>
                <button type="submit" disabled={feedbackSubmitting}>
                  {feedbackSubmitting ? 'Sending...' : 'Send'}
                </button>
              </form>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function csvCell(value) {
  const text = String(value ?? '');
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function sleep(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function lastActiveListKey(userId) {
  return `stock-analyzer:last-active-list:${userId}`;
}

function hiddenColumnsKey(userId) {
  return `stock-analyzer:hidden-columns:${userId}`;
}

function sidebarFoldsKey(userId) {
  return `stock-analyzer:sidebar-folds:${userId}`;
}

function feedbackPromptKey(userId) {
  return `stock-analyzer:feedback-prompt-dismissed:${userId}`;
}

function alertSeenKey(userId) {
  return `stock-analyzer:alerts-seen:${userId}`;
}

function latestAlertEventTimestamp(events) {
  return events.reduce((latest, event) => {
    const value = String(event?.created_at || '');
    return value > latest ? value : latest;
  }, '');
}

function markAlertEventsSeen(userId, events) {
  const latest = latestAlertEventTimestamp(events);
  if (!latest) return;
  window.localStorage.setItem(alertSeenKey(userId), latest);
}

function isAlertEventUnread(userId, event) {
  const seen = window.localStorage.getItem(alertSeenKey(userId)) || '';
  const createdAt = String(event?.created_at || '');
  return Boolean(createdAt && createdAt > seen);
}

function countUnreadAlertEvents(userId, events) {
  return events.filter((event) => isAlertEventUnread(userId, event)).length;
}

function formatAlertPrice(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number) || number <= 0) return 'N/A';
  return `$${number.toFixed(2)}`;
}

function loadHiddenColumns(userId) {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(hiddenColumnsKey(userId)) || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function loadSidebarFolds(userId) {
  const defaults = {
    watchlists: true,
    tickers: true,
    alerts: true,
    columns: false,
  };
  try {
    const parsed = JSON.parse(window.localStorage.getItem(sidebarFoldsKey(userId)) || '{}');
    return { ...defaults, ...(parsed && typeof parsed === 'object' ? parsed : {}) };
  } catch {
    return defaults;
  }
}

function shouldShowFeedbackPrompt(userId) {
  return true;
}

function dismissFeedbackPrompt(userId) {
  window.sessionStorage.setItem(feedbackPromptKey(userId), '1');
}

function isPriceStale(snapshot) {
  if (!snapshot?.symbol) return true;
  if (Number(snapshot.price || 0) <= 0) return true;
  if (!snapshot.price_updated_at) return true;
  const updatedAt = new Date(snapshot.price_updated_at);
  if (Number.isNaN(updatedAt.getTime())) return true;
  return Date.now() - updatedAt.getTime() >= PRICE_TTL_MS;
}

function jobMessage(job) {
  if (job.status === 'done') return 'Refresh complete.';
  if (job.status === 'partial') return `Refresh partially complete: ${job.error || 'some symbols failed.'}`;
  if (job.status === 'failed') return `Refresh failed: ${job.error || 'unknown error.'}`;
  return `Refresh ${job.status}.`;
}

function latestDate(rows, key) {
  const dates = rows
    .map((row) => row?.[key])
    .filter(Boolean)
    .map((value) => new Date(value))
    .filter((date) => !Number.isNaN(date.getTime()));
  if (!dates.length) return null;
  return new Date(Math.max(...dates.map((date) => date.getTime()))).toISOString();
}

function EmptyState({ text }) {
  return <div className="empty-state">{text}</div>;
}

function StockTable({ rows, columns: visibleColumns, sortConfig, setSortConfig, selectedTicker, onSelectTicker }) {
  function sortBy(key) {
    setSortConfig((current) => ({
      key,
      direction: current.key === key && current.direction === 'asc' ? 'desc' : 'asc',
    }));
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {visibleColumns.map(([key, label]) => (
              <th key={label} onClick={() => sortBy(key)} className={key === 'ticker' ? 'sticky-col' : ''}>
                {label}
                {sortConfig.key === key && <span className="sort-mark">{sortConfig.direction === 'asc' ? ' ▲' : ' ▼'}</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.ticker}
              onClick={() => onSelectTicker(row.ticker)}
              className={[
                ['Update Failed', 'Needs Cache', 'Partial', 'Missing Fundamentals'].includes(row.dataStatus) ? 'failed-row' : '',
                selectedTicker === row.ticker ? 'selected-row' : '',
              ].filter(Boolean).join(' ')}
            >
              {visibleColumns.map(([key], index) => (
                <td key={key} className={`${cellClass(key, row[key])} ${index === 0 ? 'sticky-col' : ''}`}>{row[key]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function cellClass(key, value) {
  if (key === 'revenueStatus' || key === 'profitStatus') {
    if (['N/A', 'Updating...', 'Missing'].includes(value)) return value === 'Updating...' ? 'updating' : '';
    return value === 'Growth' ? 'good' : 'bad';
  }
  if (key === 'greenCharts') {
    return value === 'Yes' ? 'good' : 'bad';
  }
  if (value === 'Updating...') {
    return 'updating';
  }
  if (key === 'ownership') {
    if (['N/A', 'Updating...', 'Missing', 'Ownership pending'].includes(value)) {
      return value === 'Updating...' ? 'updating' : '';
    }
    const num = Number(String(value).replace('%', ''));
    if (num > 75) return 'strong';
    if (num > 50) return 'watch';
    if (num > 20) return 'mid';
    return 'bad';
  }
  return '';
}

createRoot(document.getElementById('root')).render(<App />);
