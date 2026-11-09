# Oxygen Debt design

## What is implemented

Planning is complete. The optimizer implementation starts with the [baseline command](docs/WORKFLOW.md). This file will record shipped behavior as each pass lands.

## Pass order

The proposed order is local simplification, reachability, liveness and dead-code removal, then machine-specific passes. Local simplification can reveal constant branches and dead register definitions. [Technical plan](docs/TRD.md)

## Each pass

The technical plan records the proposed analyses and rewrite conditions. For each shipped pass, add its actual behavior, runtime complexity, and the facts that make its rewrites safe. Keep the references and kit attribution with the relevant pass. [Research references](docs/RESEARCH.md)

## The machine

The plan is to read the supplied machine settings before choosing fused instructions or estimating the cost of register reuse and scheduling.

## Keeping the behaviour

Every pass must preserve the ending, the ordered volatile log, and data memory at termination. Use the official validator to test those properties and add focused inputs for hazards the public samples may miss. [Software requirements](docs/SRS.md)

## Profiles

The baseline will accept an optional profile. If block layout is added, edge counts will guide placement while all control-flow targets stay intact.

## Known problems

Optimizer correctness and performance have yet to be measured. Current evidence covers the organizer examples only.
