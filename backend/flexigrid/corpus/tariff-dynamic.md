---
id: tariff-dynamic
title: Dynamic electricity contracts in Belgium — how hourly prices work
source_type: public-summary
tags: tariff, dynamic, hourly, price, contract, retail, cost
---

## Hourly contracts

A dynamic (hourly) electricity contract indexes the energy component of the retail price to the day-ahead wholesale market. Prices for all 24 hours of tomorrow are published in the afternoon, so an overnight schedule can be planned each evening with certainty about tomorrow's energy prices. On a typical day the cheapest hours fall in the early morning and around midday solar peaks; the most expensive hours fall in the evening, roughly 17:00 to 20:00.

## What the retail price contains

The consumer price per kilowatt-hour combines the wholesale-indexed energy component with network tariffs, levies, and VAT. The spread between the cheapest and most expensive hour of a day is frequently a factor of two or more, which is what makes load shifting financially meaningful for an EV-owning household.

## Imbalance prices are not consumer prices

Elia publishes imbalance prices that settle deviations between scheduled and actual positions of balance-responsible parties. These prices can spike far above or below retail levels and are sometimes negative. They are market-settlement signals, not prices a household pays. A household planner must therefore keep retail-tariff data and Elia grid data semantically separate: grid datasets indicate when the system is stressed, while only the retail tariff determines the household's cost.

## The demo tariff fixture

FlexiGrid's reproducible demonstration uses a frozen 24-value hourly retail tariff labelled as fixture data. In live operation the same interface would be filled from the day-ahead publication of the household's supplier.
