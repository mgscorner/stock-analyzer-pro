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

function shiftDays(isoDate, days) {
  const date = new Date(`${isoDate}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export default function ChartPanel({ symbol, snapshot, userId, activeList }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);
  const priceLinesRef = useRef([]);
  const [alerts, setAlerts] = useState([]);
  const [editingAlertId, setEditingAlertId] = useState('');
  const [alertInput, setAlertInput] = useState('');
  const [alertMessage, setAlertMessage] = useState('');
  const [hoverPrice, setHoverPrice] = useState(null);
  const [previewArmed, setPreviewArmed] = useState(false);
  const [savingEdit, setSavingEdit] = useState(false);

  const history = Array.isArray(snapshot?.history_data) ? snapshot.history_data : [];
  const chartData = useMemo(() => toChartData(history), [history]);
  const currentPrice = Number(snapshot?.price || 0);
  const currentLabel = displayPrice(currentPrice);
  const lastClose = chartData.length ? chartData[chartData.length - 1].value : 0;
  const referencePrice = currentPrice > 0 ? currentPrice : lastClose;
  const stepValue = Math.max(0.01, Number((referencePrice >= 100 ? 0.1 : 0.01).toFixed(2)));
  const currentAlert = alerts.find((alert) => alert.id === editingAlertId);
  const activeAlerts = alerts.filter((alert) => alert.active);
  const maxAlertsReached = alerts.length >= 4;

  useEffect(() => {
    if (!symbol || !userId) {
      setAlerts([]);
      setEditingAlertId('');
      setAlertInput('');
      setPreviewArmed(false);
      return;
    }
    loadAlerts();
  }, [symbol, userId]);

  useEffect(() => {
    const selected = currentAlert;
    if (selected) {
      setAlertInput(String(Number(selected.threshold || 0).toFixed(2)));
      setPreviewArmed(false);
      return;
    }
    if (previewArmed) {
      return;
    }
    if (referencePrice > 0) {
      setAlertInput(String(Number(referencePrice).toFixed(2)));
      return;
    }
    setAlertInput('');
    setPreviewArmed(false);
  }, [editingAlertId, currentAlert, referencePrice, previewArmed]);

  useEffect(() => {
    if (!editingAlertId || !currentAlert?.active) return undefined;
    const nextValue = Number(alertInput);
    const currentValue = Number(currentAlert.threshold || 0);
    if (!Number.isFinite(nextValue) || !Number.isFinite(currentValue)) return undefined;
    if (Number(nextValue.toFixed(2)) === Number(currentValue.toFixed(2))) return undefined;
    const timer = window.setTimeout(() => {
      updateAlertThreshold(nextValue);
    }, 150);
    return () => window.clearTimeout(timer);
  }, [alertInput, editingAlertId, currentAlert?.active, currentAlert?.threshold]);

  async function loadAlerts() {
    const { data, error } = await supabase
      .from('alerts')
      .select('id,symbol,condition_type,threshold,active,last_triggered_at,interval_minutes')
      .eq('user_id', userId)
      .eq('symbol', symbol)
      .order('created_at');
    if (error) {
      setAlertMessage(`Alert load failed: ${error.message}`);
      return;
    }
    const next = sortAlerts(data || []);
    setAlerts(next);
    setEditingAlertId((current) => (next.some((row) => row.id === current) ? current : ''));
    setAlertMessage('');
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
    const lastTime = chartData[chartData.length - 1].time;
    const targetFrom = shiftDays(lastTime, -183);
    const fromIndex = Math.max(
      0,
      chartData.findIndex((row) => row.time >= targetFrom)
    );
    chart.timeScale().setVisibleRange({
      from: chartData[fromIndex].time,
      to: lastTime,
    });
    chartRef.current = chart;
    seriesRef.current = series;
    chart.subscribeCrosshairMove((param) => {
      if (!param?.point || param.point.y == null) return;
      const price = series.coordinateToPrice(param.point.y);
      if (!Number.isFinite(price) || price <= 0) return;
      setHoverPrice(Number(price.toFixed(2)));
    });

    return () => {
      priceLinesRef.current = [];
      chartRef.current = null;
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
      const isSelected = alert.id === editingAlertId;
      const liveThreshold = isSelected && alertInput ? Number(alertInput) : Number(alert.threshold || 0);
      const threshold = Number.isFinite(liveThreshold) && liveThreshold > 0 ? liveThreshold : Number(alert.threshold || 0);
      if (!Number.isFinite(threshold) || threshold <= 0) return;
      const isBelow = String(alert.condition_type || '').toLowerCase() === 'price_below';
      priceLinesRef.current.push(
        series.createPriceLine({
          price: threshold,
          color: isBelow ? '#8b1e1e' : '#f59e0b',
          lineWidth: isSelected ? 3 : 2,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: isSelected,
          title: isSelected ? `Alert ${index + 1}` : '',
        })
      );
    });

    const preview = Number(alertInput);
    if (previewArmed && !editingAlertId && Number.isFinite(preview) && preview > 0) {
      priceLinesRef.current.push(
        series.createPriceLine({
          price: preview,
          color: '#2f6fed',
          lineWidth: 2,
          lineStyle: LineStyle.Solid,
          axisLabelVisible: true,
          title: 'Preview',
        })
      );
    }
  }, [activeAlerts, editingAlertId, currentPrice, alertInput, currentAlert, previewArmed]);

  if (!symbol) {
    return <div className="chart-panel muted">Select a row to show its cached chart.</div>;
  }

  if (!chartData.length) {
    return <div className="chart-panel muted">{symbol}: no cached chart history yet.</div>;
  }

  function inferConditionType(value) {
    if (referencePrice <= 0) return null;
    if (value > referencePrice) return 'price_above';
    if (value < referencePrice) return 'price_below';
    return null;
  }

  async function saveAlert() {
    setAlertMessage('');
    const value = Number(alertInput);
    if (!Number.isFinite(value) || value <= 0) {
      setAlertMessage('Enter a valid alert price.');
      return;
    }

    const conditionType = inferConditionType(value);
    if (!conditionType) {
      setAlertMessage('Alert price must be above or below the current price.');
      return;
    }

    if (editingAlertId && currentAlert?.active) {
      await updateAlertThreshold(value);
      return;
    }

    if (maxAlertsReached) {
      setAlertMessage('Maximum 4 alerts per chart.');
      return;
    }

    const payload = {
      user_id: userId,
      symbol,
      watchlist_name: activeList || null,
      condition_type: conditionType,
      threshold: value,
      interval_minutes: 1,
      active: true,
    };

    const { data, error } = await supabase
      .from('alerts')
      .insert([payload])
      .select('id,symbol,condition_type,threshold,active,last_triggered_at,interval_minutes')
      .single();
    if (error) {
      setAlertMessage(`Alert insert failed: ${error.message}`);
      return;
    }
    const next = sortAlerts([...alerts, data]);
    setAlerts(next);
    setEditingAlertId(data.id);
    setPreviewArmed(false);
    setAlertMessage('Alert created.');
  }

  async function updateAlertThreshold(value) {
    const conditionType = inferConditionType(value);
    if (!conditionType) {
      setAlertMessage('Alert price must be above or below the current price.');
      return;
    }
    setSavingEdit(true);
    const { data, error } = await supabase
      .from('alerts')
      .update({
        threshold: value,
        condition_type: conditionType,
        active: true,
        updated_at: new Date().toISOString(),
      })
      .eq('id', editingAlertId)
      .select('id,symbol,condition_type,threshold,active,last_triggered_at,interval_minutes')
      .single();
    setSavingEdit(false);
    if (error) {
      setAlertMessage(`Alert update failed: ${error.message}`);
      return;
    }
    const next = sortAlerts(alerts.map((alert) => (alert.id === editingAlertId ? data : alert)));
    setAlerts(next);
    setAlertMessage('Alert updated.');
  }

  async function removeAlert() {
    if (!editingAlertId) return;
    setAlertMessage('');

    const removeId = editingAlertId;
    const next = alerts.filter((alert) => alert.id !== removeId);
    setAlerts(next);
    setEditingAlertId(next[0]?.id || '');
    setPreviewArmed(false);

    if (next[0]) {
      setAlertInput(String(Number(next[0].threshold || 0).toFixed(2)));
    } else if (referencePrice > 0) {
      setAlertInput(String(Number(referencePrice).toFixed(2)));
    } else {
      setAlertInput('');
    }

    const { error } = await supabase.from('alerts').delete().eq('id', removeId);
    if (error) {
      setAlertMessage(`Alert delete failed: ${error.message}`);
      await loadAlerts();
      return;
    }

    setAlertMessage('Alert removed.');
  }

  async function reactivateAlert() {
    if (!editingAlertId) return;
    setAlertMessage('');
    const { data, error } = await supabase
      .from('alerts')
      .update({ active: true, updated_at: new Date().toISOString() })
      .eq('id', editingAlertId)
      .select('id,symbol,condition_type,threshold,active,last_triggered_at,interval_minutes')
      .single();
    if (error) {
      setAlertMessage(`Alert reactivate failed: ${error.message}`);
      return;
    }
    const next = sortAlerts(alerts.map((alert) => (alert.id === editingAlertId ? data : alert)));
    setAlerts(next);
    setAlertMessage('Alert reactivated.');
  }

  function armCreateModeAt(value) {
    if (!Number.isFinite(value) || value <= 0) return;
    setEditingAlertId('');
    setAlertInput(String(Number(value).toFixed(2)));
    setPreviewArmed(true);
    setAlertMessage('Preview moved. Click Create Alert to save it.');
  }

  function selectAlertForEdit(alert) {
    setEditingAlertId(alert.id);
    setAlertInput(String(Number(alert.threshold || 0).toFixed(2)));
    setPreviewArmed(false);
    setAlertMessage('Editing selected alert.');
  }

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
        <label className="alert-input-group alert-input-group-edit">
          <span>Alert Price</span>
          <input
            type="number"
            step={stepValue}
            min="0.01"
            value={alertInput}
            onChange={(event) => {
              setAlertInput(event.target.value);
              if (!editingAlertId) {
                setPreviewArmed(true);
              }
            }}
            onKeyDown={(event) => {
              if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
                event.stopPropagation();
              }
            }}
            onWheel={(event) => {
              if (document.activeElement === event.currentTarget) {
                event.stopPropagation();
              }
            }}
          />
          <button type="button" className="ghost" onClick={saveAlert}>
            {editingAlertId && currentAlert?.active ? 'Update Alert' : 'Create Alert'}
          </button>
        </label>
        <button
          type="button"
          className="ghost"
          disabled={!editingAlertId || currentAlert?.active}
          onClick={reactivateAlert}
        >
          Reactivate
        </button>
        <button type="button" className="ghost danger" disabled={!editingAlertId} onClick={removeAlert}>
          Remove Alert
        </button>
        <select value={editingAlertId} onChange={(event) => {
          const id = event.target.value;
          if (!id) {
            setEditingAlertId('');
            if (referencePrice > 0) {
              setAlertInput(String(Number(referencePrice).toFixed(2)));
            } else {
              setAlertInput('');
            }
            setPreviewArmed(false);
            setAlertMessage('');
            return;
          }
          const alert = alerts.find((row) => row.id === id);
          if (alert) selectAlertForEdit(alert);
        }}>
          <option value="">New alert</option>
          {alerts.map((alert, index) => (
            <option key={alert.id} value={alert.id}>
              {`Alert ${index + 1} - ${alert.condition_type === 'price_below' ? 'Below' : 'Above'} - ${displayPrice(alert.threshold)} - ${alert.active ? 'Active' : 'Triggered'}`}
            </option>
          ))}
        </select>
      </div>
      <div
        ref={containerRef}
        className="history-chart-advanced"
        aria-label={`${symbol} chart`}
        onContextMenu={(event) => {
          event.preventDefault();
          if (hoverPrice) armCreateModeAt(hoverPrice);
        }}
      />
      <div className="chart-alert-status">
        {alertMessage || (!editingAlertId && maxAlertsReached ? 'Maximum 4 alerts reached. Remove one to create another.' : ' ')}
      </div>
      {savingEdit ? <div className="chart-alert-status">Saving alert...</div> : null}
    </section>
  );
}
