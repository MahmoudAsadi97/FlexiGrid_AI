---
id: elia-ods002
title: Elia Open Data ods002 — measured and forecast total load
source_type: public-summary
tags: elia, load, forecast, grid, belgian, dataset
---

## What the dataset contains

Dataset ods002 on the Elia Open Data portal provides the measured total load of the Belgian control area together with Elia's most recent forecast, day-ahead forecast, and week-ahead forecast. Values are published per quarter-hour in megawatts and updated continuously. Total load approximates the electricity demand that the transmission system must serve at each moment.

## How FlexiGrid uses it

FlexiGrid reads the day-ahead total-load forecast as the demand half of its grid-stress signal: hours where forecast load is high relative to the daily range contribute to a higher stress score. Because the values describe the national system, they indicate when the grid as a whole is under pressure; they say nothing about an individual household's bill.

## Access

Records are available without authentication from the Opendatasoft records endpoint under the dataset identifier ods002, ordered by datetime, with a JSON response containing one record per quarter-hour.
