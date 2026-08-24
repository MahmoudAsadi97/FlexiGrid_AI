---
id: solar-battery
title: Home battery and PV self-consumption basics
source_type: synthetic-representative
tags: solar, battery, pv, self-consumption, inverter
---

## Self-consumption

A rooftop PV installation produces most of its energy around midday. Without storage, a typical Belgian household consumes 30 to 40 percent of its own production directly; the rest is injected into the grid. Shifting flexible appliances into the solar window raises self-consumption without any additional hardware.

## Home batteries

A residential battery of 5 to 10 kWh charges from surplus PV and discharges in the evening. Round-trip efficiency is around 90 percent. Under the Flemish capacity tariff a battery can also cap the monthly quarter-hour peak by discharging while a large appliance runs, a strategy known as peak shaving.

## Inverter limits

The hybrid inverter limits combined charge and discharge power, commonly to 5 kW. A planner that controls both a battery and large appliances must model the inverter limit separately from the grid-connection limit. The current FlexiGrid prototype does not schedule a battery; this document exists so that retrieval can distinguish battery questions from appliance-scheduling questions.
