---
id: elia-ods201
title: Elia Open Data ods201 — actual generation by fuel type
source_type: public-summary
tags: elia, generation, fuel, mix, nuclear, gas, dataset
---

## What the dataset contains

Dataset ods201 reports actual electricity generation in the Belgian control area aggregated by fuel type, including nuclear, natural gas, wind, solar, hydro, and others, per quarter-hour in megawatts. It describes what actually ran, as opposed to the forecast datasets that describe what is expected.

## How FlexiGrid uses it

The generation mix provides context in the interface and a path towards a carbon-aware objective: hours where low-carbon sources dominate the mix are attractive hours for flexible consumption. The current prototype displays the mix and reserves the carbon-weighted objective for future work; the optimization objectives shipped today weigh retail cost and the load-and-wind stress signal.

## Access

Records are available without authentication from the Opendatasoft records endpoint under the dataset identifier ods201. Because the dataset is retrospective, FlexiGrid treats it as context rather than as a planning input for tomorrow.
