# What this replaces

> **Note on scope.** This file describes the capability gap `precedent` fills. It deliberately names
> no vendor and quotes no price. Comparative analysis of commercial products is maintained outside
> this repository for now. Nothing in the tool, its help text, its command output, or any hosted
> page may name or price a commercial product — see `docs/program/CONVENTIONS.md`.

## Two halves, and only one of them has any competition

### Half one: federal award history

Subscription products in this category do surface federal award history in some form. What they
generally do not surface, and what a first-time applicant actually needs, is the **new-entrant
rate** — the share of each year's winners that had never won the program before.

Median award size tells you whether you are in the right weight class. The new-entrant rate tells
you whether the door is open at all. A program with a healthy median and a new-entrant rate near
zero is a closed shop with good optics, and advising a client into it costs them a hundred unpaid
hours. That statistic is the headline output of this tool for exactly that reason.

The underlying data is free and unauthenticated. `precedent history` needs no key.

### Half two: the pass-through layer, where there is no competition at all

Most federal money that reaches a small nonprofit arrives as a **subaward** passed through a state
agency, a university, a county, or a larger nonprofit. That layer is invisible in commercial grant
research products — not because they are careless, but because the data lives somewhere they do not
look: the Schedule of Expenditures of Federal Awards inside single audit filings.

Given a state and a program area, `precedent passthrough` names the organizations receiving federal
money and passing it down. That is a prospect list nobody currently sells, and it is the most
defensible idea in this repository.

## The honesty constraint that comes with it

Single audit filings exist only for organizations above the audit threshold, which the 2024 Uniform
Guidance revision raised for fiscal years beginning on or after 2024-10-01. Organizations below it
do not file, so coverage is **inherently partial**.

Every pass-through result carries a coverage object stating what fraction of the relevant universe
was observable. No compact mode, no `--quiet`, and no JSON shape omits it. Estimating, imputing, or
smoothing over that gap is the fastest way to destroy the tool's credibility, and it is on the
stop-and-ask list for that reason.

## What `precedent` does not claim

- It does not say whether a client is a good fit for a program. It reports what happened.
- It does not predict award outcomes.
- Pass-through coverage is partial by construction, and says so everywhere it appears.
