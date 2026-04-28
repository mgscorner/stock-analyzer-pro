# Quick User Guide

This guide explains how to use the app at a practical level.

## What The App Does

The app helps you manage stock watchlists, review core company data, and set price alerts.

It is a prototype, but it is usable.

## Important Expectation

The app is **not real-time**.

- Prices refresh on a schedule.
- Alerts are checked on a schedule.
- Some values may update a little after the table first appears.
- Revenue, profit, ownership, and chart history are cached data and may not refresh at the same speed as price.

Use it as a research and monitoring tool, not as a live trading terminal.

## Signing In

After login, the app loads your watchlists and your saved data.

## Watchlists

Use **Manage Watchlists** to:

- create a watchlist
- switch between watchlists
- delete a watchlist

When you switch watchlists, the app loads the saved data for that list.

## Tickers

Use **Manage Tickers** to:

- add a ticker to the current watchlist
- write a note for the selected ticker
- remove the selected ticker from the current watchlist

To manage a ticker note, first click the ticker row in the table. The selected ticker then appears in the manage area.

## Reading The Table

The table shows the saved data the app currently has for each ticker.

Typical fields include:

- latest price
- revenue and profit trend status
- ownership percentage
- performance metrics
- revenue and profit history
- market cap

If some fields are still missing, the app may show `N/A`, `Updating...`, or similar status text until that data is available.

## Chart

Click a ticker row to open its chart.

The chart is mainly a historical view with the latest known price connected at the end.

The chart is useful for context, but it is not a tick-by-tick live feed.

## Alerts

You can create price alerts from the chart.

Basic flow:

1. Click a ticker row to open the chart.
2. Right-click the chart near the price level you want.
3. Adjust the alert price if needed.
4. Click **Create Alert**.

You can also:

- select an existing alert from the dropdown
- change its price
- update it
- remove it
- reactivate it after it has triggered

Triggered alerts appear in **Manage Alerts** in the sidebar.

If you click a triggered alert, the app opens that ticker and selects the related alert in the chart.

## Comments

Each ticker can have a note in the current watchlist.

Comments are there to help you remember why the ticker is on the list or what you want to watch.

## Feedback

You can send feedback from the app.

Use that for:

- bugs
- feature ideas
- general feedback

## Current Prototype Limits

Keep these limits in mind:

- not real-time
- some data updates faster than other data
- alerts are checked on intervals, not continuously
- some company data may appear later than price data
- chart detail is limited compared with a full trading platform

That is expected for this version.
