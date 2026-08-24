---
id: manual-ev
title: Wallbox EVL-7 EV charger — installation and scheduling manual (extract)
source_type: synthetic-representative
tags: ev, charger, charging, vehicle, schedule, eco
---

## Charging modes and power draw

The EVL-7 wallbox charges in three modes. Boost mode draws 7.4 kW on a single-phase 32 A circuit and is intended for occasional fast top-ups. Standard mode draws 5.5 kW. Eco mode limits the draw to 3.6 kW, which reduces the load on the household connection and is the recommended setting for overnight charging. The unit measures energy per session with a built-in MID-certified meter.

## Scheduled charging

The charger supports scheduled charging in one-hour blocks through the local API or the companion app. A schedule consists of a start hour, a duration, and a mode. In eco mode, a two-hour block delivers approximately 7.2 kWh into the battery after conversion losses. Schedules survive a power interruption: the wallbox resumes the remaining block when supply returns.

## Load balancing and connection limits

When an external energy-management system controls the wallbox, it must ensure that the combined household load, including the charger, stays below the connection capacity configured by the installer. The wallbox accepts a dynamic current limit signal and will reduce or pause charging within five seconds of receiving a lower limit. Pausing charging does not damage the vehicle battery.

## Battery care recommendations

For daily use, charging to 80 percent state of charge extends battery life. Complete the charge at least 30 minutes before departure in cold weather so that battery preconditioning can run from mains power rather than from the battery itself.
