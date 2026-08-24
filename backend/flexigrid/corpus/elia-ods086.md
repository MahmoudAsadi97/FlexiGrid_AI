---
id: elia-ods086
title: Elia Open Data ods086 — wind power production and forecast
source_type: public-summary
tags: elia, wind, forecast, renewable, dataset
---

## What the dataset contains

Dataset ods086 provides Elia's estimation of actual wind power production in Belgium together with intraday, day-ahead, and week-ahead forecasts. Values are published per quarter-hour in megawatts, split by onshore and offshore where available, and include the monitored installed capacity used for the estimation.

## How FlexiGrid uses it

The day-ahead wind forecast is the supply half of FlexiGrid's grid-stress signal. Hours with strong forecast wind relative to installed capacity lower the stress score, because demand in those hours is more likely to be covered by renewable generation. Scheduling flexible household load into high-wind hours therefore supports the system and typically correlates with lower day-ahead prices.

## Access

Records are available without authentication from the Opendatasoft records endpoint under the dataset identifier ods086. Forecasts for tomorrow are complete by the evening before, which is sufficient for FlexiGrid's overnight planning horizon.
