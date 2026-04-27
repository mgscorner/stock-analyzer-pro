import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createChart, CrosshairMode, LineStyle } from 'lightweight-charts';

function alarmStorageKey(userId, symbol) {
  return `stock-analyzer:chart-alarms:${userId}:${symbol}`;
}

function loadAlarms(userId, symbol) {
  try {
    const raw = window.localStorage.getItem(alarmStorageKey(userId, symbol));
    const parsed = JSON.parse(raw || '[]');
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((value) => Number(value))
      .filter((value) => Number.isFinite(value) && value > 0)
      .sort((a, b) => a - b);
  } catch {
    return [];
  }
}

function saveAlarms(userId, symbol, alarms) {
  window.localStorage.setItem(alarmStorageKey(userId, symbol), JSON.stringify(alarms));
}

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

export default function ChartPanel({ symbol, snapshot, userId }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);
  const priceLinesRef = useRef([]);
  const [alarms, setAlarms] = useState([]);
  const [selectedAlarm, setSelectedAlarm] = useState(-1);

  const history = Array.isArray(snapshot?.history_data) ? snapshot.history_data : [];
  const chartData = useMemo(() => toChartData(history), [history]);
  const currentPrice = Number(snapshot?.price || 0);
  const currentLabel = displayPrice(currentPrice);
  const lastClose = chartData.length ? chartData[chartData.length - 1].value : 0;

  useEffect(() => {
    if (!symbol) {
      setAlarms([]);
      setSelectedAlarm(-1);
      return;
    }
    const next = loadAlarms(userId, symbol);
    setAlarms(next);
    setSelectedAlarm(next.length ? 0 : -1);
  }, [userId, symbol]);

  useEffect(() => {
    if (!symbol) return;
    saveAlarms(userId, symbol, alarms);
    if (selectedAlarm >= alarms.length) {
      setSelectedAlarm(alarms.length ? alarms.length - 1 : -1);
    }
  }, [alarms, selectedAlarm, symbol, userId]);

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

    const series = chart.addAreaSeries({
      lineColor: '#1d6f42',
      topColor: 'rgba(29, 111, 66, 0.24)',
      bottomColor: 'rgba(29, 111, 66, 0.03)',
      lineWidth: 2,
      priceLineVisible: true,
      lastValueVisible: true,
    });

    series.setData(chartData);

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

    chart.timeScale().fitContent();

    chartRef.current = chart;
    seriesRef.current = series;

    return () => {
      priceLinesRef.current = [];
      seriesRef.current = null;
      chartRef.current = null;
      chart.remove();
    };
  }, [chartData, currentPrice]);

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

    alarms.forEach((alarmPrice, index) => {
      priceLinesRef.current.push(
        series.createPriceLine({
          price: alarmPrice,
          color: index === selectedAlarm ? '#b42318' : '#f97316',
          lineWidth: index === selectedAlarm ? 2 : 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: `Alert ${index + 1}`,
        })
      );
    });
  }, [alarms, selectedAlarm, currentPrice]);

  if (!symbol) {
    return <div className="chart-panel muted">Select a row to show its cached chart.</div>;
  }

  if (!chartData.length) {
    return <div className="chart-panel muted">{symbol}: no cached chart history yet.</div>;
  }

  function addAlarm() {
    const base = currentPrice > 0 ? currentPrice : lastClose;
    if (!base || !Number.isFinite(base)) return;
    const rounded = Number(base.toFixed(2));
    setAlarms((current) => {
      const next = [...current, rounded].sort((a, b) => a - b);
      setSelectedAlarm(next.indexOf(rounded));
      return next;
    });
  }

  function moveAlarm(direction) {
    if (selectedAlarm < 0 || selectedAlarm >= alarms.length) return;
    const current = alarms[selectedAlarm];
    const step = Math.max(0.01, Number((current * 0.01).toFixed(2)));
    const updated = Math.max(0.01, Number((current + step * direction).toFixed(2)));
    setAlarms((existing) => {
      const next = [...existing];
      next[selectedAlarm] = updated;
      return next.sort((a, b) => a - b);
    });
  }

  function removeAlarm() {
    if (selectedAlarm < 0 || selectedAlarm >= alarms.length) return;
    setAlarms((current) => current.filter((_value, index) => index !== selectedAlarm));
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
        <button className="ghost" onClick={addAlarm}>Add Alert</button>
        <button className="ghost" disabled={selectedAlarm < 0} onClick={() => moveAlarm(1)}>Alert Up</button>
        <button className="ghost" disabled={selectedAlarm < 0} onClick={() => moveAlarm(-1)}>Alert Down</button>
        <button className="ghost danger" disabled={selectedAlarm < 0} onClick={removeAlarm}>Remove Alert</button>
        <select
          value={selectedAlarm >= 0 ? String(selectedAlarm) : ''}
          onChange={(event) => setSelectedAlarm(event.target.value === '' ? -1 : Number(event.target.value))}
        >
          <option value="">Select alert</option>
          {alarms.map((alarmPrice, index) => (
            <option key={`${alarmPrice}-${index}`} value={String(index)}>
              {`Alert ${index + 1} - ${displayPrice(alarmPrice)}`}
            </option>
          ))}
        </select>
      </div>
      <div ref={containerRef} className="history-chart-advanced" aria-label={`${symbol} chart`} />
    </section>
  );
}
