---
id: pipeline-stress
title: FlexiGrid grid-stress signal — derivation methodology
source_type: project-doc
tags: stress, signal, derivation, pipeline, normalization
---

## Definition

The grid-stress signal is a 24-value hourly index from 0 to 100 describing how loaded the Belgian system is expected to be relative to available wind. It is derived, not measured: stress(h) rises with the day-ahead total-load forecast (ods002) for hour h and falls with the day-ahead wind forecast (ods086) for the same hour.

## Derivation steps

Quarter-hour forecasts for the planning day are averaged into hourly values. Hourly load and wind are min-max normalized over the day. The raw stress is the normalized load minus half the normalized wind, and the result is rescaled to 0–100 and rounded to integers. The one-half wind weight reflects that wind covers only part of Belgian demand; it is a documented modelling choice, not a physical constant.

## Provenance rules

Every stress series carries provenance: the mode field says whether it came from live records or from the frozen fixture, and live series record the retrieval timestamp and dataset identifiers. The frozen fixture used in examinations is labelled as representative demo data and is never presented as a live Elia observation.

## Limitations

The signal ignores solar generation, imports, and outages, and national stress does not always match local distribution-grid conditions. It is a demonstration-grade signal for ranking hours within one day, not a dispatch-grade metric.
