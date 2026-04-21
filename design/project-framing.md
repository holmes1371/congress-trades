# Project framing

Standing framing note for the congress-trades project. Read this at the start of any session before proposing features, scoring changes, or claims about strategy performance. Its purpose is to keep the project grounded in what the public evidence actually supports, so design decisions compound rather than drift.

This is a standing note, not a per-feature design note. It is referenced from `ROADMAP.md` and revised only when the underlying evidence base changes (new peer-reviewed work, a material regulatory shift, NANC/KRUZ being delisted, etc.) — not per-feature.

## What this project is

A research platform for testing whether a specific curated subset of Congress provides a usable trading signal, measured against the right benchmarks, after costs. The output is structured answers to a viability question — not a mirror-trading product and not investment advice. The platform's value persists even if the eventual conclusion is "the edge isn't there"; that conclusion is itself a useful answer, and the infrastructure that produces it (fetching, scoring, reporting, archiving) remains reusable regardless of the sign of the result.

## The central hazard: disclosure lag

The STOCK Act gives members up to 45 days to disclose a transaction. Peer-reviewed work (Eggers & Hainmueller; Belmont; more recent replications) finds that once the window between trade date and disclosure date is removed, much of the headline "Congress beats the market" alpha shrinks, and in some samples inverts. Returns measured from the trade date are the returns the member captured — not the returns a follower could capture by mirroring after disclosure.

Implication for the scoring pipeline: trade-date alpha is a historical artifact, not a copyable signal. Any claim the platform makes about a member's usefulness to a follower must be grounded in post-file alpha — returns measured from the later of publication date or trade date + a small entry buffer. The existing trade-date columns are fine to keep as historical context; follower-facing rankings must not rely on them.

## The right benchmarks

Two ETFs already implement a mirror strategy with institutional execution: NANC (Democratic-leaning congressional trades) and KRUZ (Republican-leaning). They are liquid and publicly priced. Any curated follow list produced by this platform has to clear the bar set by those ETFs after fees, taxes, and slippage; if it does not, the defensible conclusion is that the curated list has not added value over the off-the-shelf product. SPY and QQQ are the broader-market reference points. These four — NANC, KRUZ, SPY, QQQ — are the benchmarks the weekly report should surface against cumulative mirror PnL, so the value-add question remains visible rather than deferred.

## What this project is not

Not investment advice. Not a guarantee of alpha. Not a claim that the academic consensus on congressional trading is settled — it is not, and the post-STOCK-Act evidence is meaningfully weaker than the consumer-media narrative typically implies. Not a replacement for NANC or KRUZ. Not a live trading system; signals surfaced by the pipeline are research outputs that a user can choose to paper-trade, ignore, or investigate further.

## How this note is used

Agents read this note at the start of any session that references the roadmap, the next feature, or any strategy claim. It is not a design spec — it is the frame that keeps design specs honest. When a backlog item or user request implicitly assumes a "follow Congress equals alpha" worldview, return to this note and reframe the item around viability testing rather than yield extraction. When sizing how ambitious a feature should be, weigh it against the central hazard above: features that make failure modes visible (post-file alpha, NANC/KRUZ benchmarking, signal-quality filters, transaction-cost modeling, paper-trading logs) compound faster than features that polish the surface.
