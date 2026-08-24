---
id: safety-load
title: Residential load management and connection safety
source_type: synthetic-representative
tags: safety, load, breaker, circuit, connection, limit
---

## Connection ratings

A common Belgian single-phase residential connection is rated 40 A at 230 V, roughly 9.2 kW. The main breaker trips when sustained demand exceeds the rating. Well before that point, high sustained currents warm cabling and cost money under a capacity-based network tariff, which is why an energy-management system plans against a working limit far below the physical rating.

## Diversity and simultaneity

Not all appliances draw their nameplate power at once; ovens cycle, washers heat only briefly. Planning with hourly average power per appliance is adequate for cost and capacity purposes, but the manager must still avoid stacking devices whose heating peaks can coincide, such as starting the washing machine and the dishwasher in the same quarter-hour as an EV charge in boost mode.

## Fail-safe behaviour

If the energy-management system loses contact with a controlled device, the device must fall back to its own safe default program. Advisory planners that do not command devices, like the FlexiGrid prototype, avoid this class of risk entirely: a wrong plan costs money but cannot create an unsafe electrical state.
