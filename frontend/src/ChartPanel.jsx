import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createChart, CrosshairMode, LineStyle, AreaSeries } from 'lightweight-charts';
import { supabase } from './supabaseClient';

function toChartData(history) {
  return history
    .map((row) => {
      const time = String(row?.date || '').trim();
      const value = Number(row?.close || 0);
      if (!time || !Number.isFinite(value) || value <= 0) return null;
      return { time, value };
    })
    .filter(Boolean);
}

function displayPrice(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number) || number <= 0) return 'N/A';
  return `$${number.toFixed(2)}`;
}

function sortAlerts(rows) {
  return [...rows].sort((a, b) => {
    if (Boolean(a.active) !== Boolean(b.active)) return a.active ? -1 : 1;
    return Number(a.threshold || 0) - Number(b.threshold || 0);
  });
}

export default function ChartPanel({ symbol, snapshot, userId, activeList }) {
  const containerRef = useRef(null);
  const seriesRef = useRef(null);
  const priceLinesRef = useRef([]);
  const [alerts, setAlerts] = useState([]);
  const [selectedAlert, setSelectedAlert] = useState('');

  const history = Array.isArray(snapshot?.history_data) ? snapshot.history_data : [];
  const chartData = useMemo(() => toChartData(history), [history]);
  const currentPrice = Number(snapshot?.price || 0);
  const currentLabel = displayPrice(currentPrice);
  const lastClose = chartData.length ? chartData[chartData.length - 1].value : 0;
  const activeAlerts = alerts.filter((alert) => alert.active);

  useEffect(() => {
    if (!symbol || !userId) {
      setAlerts([]);
      setSelectedAlert('');
      return;
    }
    loadAlerts();
  }, [symbol, userId]);

  async function loadAlerts() {
    const { data, error } = await supabase
      .from('alerts')
      .select('id,symbol,condition_type,threshold,active,last_triggered_at,interval_minutes')
      .eq('user_id', userId)
      .eq('symbol', symbol)
      .order('created_at');
    if (error) {
      console.warn('alert load failed', error.message);
      return;
    }
    const next = sortAlerts(data || []);
    setAlerts(next);
    if (!next.find((row) => row.id === selectedAlert)) {
      setSelectedAlert(next[0]?.id || '');
    }
  }

  useEffect(() => {
    if (!containerRef.current || !chartData.length) return undefined;

    const chart = createChart(containerRef.current, {
      autoSize: true,
      height: 280,
      layout: {
        background: { color: '#ffffff' },
        textColor: '#1d2430',
      },
      grid: {
        vertLines: { color: '#eef2f5' },
        horzLines: { color: '#eef2f5' },
      },
      rightPriceScale: {
        borderColor: '#dce2e8',
      },
      timeScale: {
        borderColor: '#dce2e8',
        timeVisible: false,
      },
      crosshair: {
        mode: CrosshairMode.Normal,
      },
    });

    const series = chart.addSeries(AreaSeries, {
      lineColor: '#1d6f42',
      topColor: 'rgba(29, 111, 66, 0.24)',
      bottomColor: 'rgba(29, 111, 66, 0.03)',
      lineWidth: 2,
      priceLineVisible: true,
      lastValueVisible: true,
    });

    series.setData(chartData);
    chart.timeScale().fitContent();
    seriesRef.current = series;

    return () => {
      priceLinesRef.current = [];
      seriesRef.current = null;
      chart.remove();
    };
  }, [chartData]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    for (const line of priceLinesRef.current) {
      try {
        series.removePriceLine(line);
      } catch {}
    }
    priceLinesRef.current = [];

    if (currentPrice > 0) {
      priceLinesRef.current.push(
        series.createPriceLine({
          price: currentPrice,
          color: '#1d2430',
          lineWidth: 1,
          lineStyle: LineStyle.Dotted,
          axisLabelVisible: true,
          title: 'Current',
        })
      );
    }

    activeAlerts.forEach((alert, index) => {
      const threshold = Number(alert.threshold || 0);
      if (!Number.isFinite(threshold) || threshold <= 0) return;
      priceLinesRef.current.push(
        series.createPriceLine({
          price: threshold,
          color: alert.id === selectedAlert ? '#b42318' : '#f97316',
          lineWidth: alert.id === selectedAlert ? 2 : 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: `Alert ${index + 1}`,
        })
      );
    });
  }, [activeAlerts, selectedAlert, currentPrice]);

  if (!symbol) {
    return <div className="chart-panel muted">Select a row to show its cached chart.</div>;
  }

  if (!chartData.length) {
    return <div className="chart-panel muted">{symbol}: no cached chart history yet.</div>;
  }

  async function addAlert() {
    const base = currentPrice > 0 ? currentPrice : lastClose;
    if (!base || !Number.isFinite(base)) return;
    const rounded = Number(base.toFixed(2));
    const payload = {
      user_id: userId,
      symbol,
      watchlist_name: activeList || null,
      condition_type: 'price_above',
      threshold: rounded,
      interval_minutes: 1,
      active: true,
    };
    const { error } = await supabase.from('alerts').insert(payload);
    if (error) {
      console.warn('alert insert failed', error.message);
      return;
    }
    await loadAlerts();
  }

  async function moveAlert(direction) {
    const current = alerts.find((alert) => alert.id === selectedAlert);
    if (!current) return;
    const base = Number(current.threshold || 0);
    const step = Math.max(0.01, Number((base * 0.01).toFixed(2)));
    const updated = Math.max(0.01, Number((base + step * direction).toFixed(2)));
    const { error } = await supabase
      .from('alerts')
      .update({ threshold: updated, active: true, updated_at: new Date().toISOString() })
      .eq('id', current.id);
    if (error) {
      console.warn('alert update failed', error.message);
      return;
    }
    await loadAlerts();
  }

  async function removeAlert() {
    if (!selectedAlert) return;
    const { error } = await supabase.from('alerts').delete().eq('id', selectedAlert);
    if (error) {
      console.warn('alert delete failed', error.message);
      return;
    }
    await loadAlerts();
  }

  async function reactivateAlert() {
    if (!selectedAlert) return;
    const { error } = await supabase
      .from('alerts')
      .update({ active: true, updated_at: new Date().toISOString() })
      .eq('id', selectedAlert);
    if (error) {
      console.warn('alert reactivate failed', error.message);
      return;
    }
    await loadAlerts();
  }

  const currentAlert = alerts.find((alert) => alert.id === selectedAlert);

  return (
    <section className="chart-panel">
      <div className="chart-header">
        <div className="chart-title">
          <strong>{symbol}</strong>
          <span>{currentLabel}</span>
        </div>
        <span>Cached history with live table price line</span>
      </div>
      <div className="chart-toolbar">
        <button className="ghost" onClick={addAlert}>Add Alert</button>
        <button className="ghost" disabled={!selectedAlert || !currentAlert?.active} onClick={() => moveAlert(1)}>Alert Up</button>
        <button className="ghost" disabled={!selectedAlert || !currentAlert?.active} onClick={() => moveAlert(-1)}>Alert Down</button>
        <button className="ghost" disabled={!selectedAlert || currentAlert?.active} onClick={reactivateAlert}>Reactivate</button>
        <button className="ghost danger" disabled={!selectedAlert} onClick={removeAlert}>Remove Alert</button>
        <select value={selectedAlert} onChange={(event) => setSelectedAlert(event.target.value)}>
          <option value="">Select alert</option>
          {alerts.map((alert, index) => (
            <option key={alert.id} value={alert.id}>
              {`Alert ${index + 1} - ${displayPrice(alert.threshold)} - ${alert.active ? 'Active' : 'Triggered'}`}
            </option>
          ))}
        </select>
      </div>
      <div ref={containerRef} className="history-chart-advanced" aria-label={`${symbol} chart`} />
    </section>
  );
}
