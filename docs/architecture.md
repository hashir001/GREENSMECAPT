# GREENSMECAPT Architecture

GREENSMECAPT is an evidence-aware decision-support platform for assessing and
ranking green SMEs.

## Package responsibilities

### `domain`

Defines the platform's core concepts and rules, including SMEs, criteria,
evidence, assessments, expert judgments, and ranking results.

### `mcdm`

Contains the mathematical decision-support methods, including fuzzy-number
representation, fuzzy DEMATEL, TOPSIS, and ELECTRE III.

### `data`

Handles external data ingestion, validation, transformation, and persistence.

### `services`

Coordinates complete application use cases by combining domain objects, data
operations, and decision methods.

### `api`

Exposes application workflows to future user interfaces and external systems.

## Dependency direction

```mermaid
flowchart TD
    API["API"] --> Services["Application services"]
    Services --> Domain["Domain models"]
    Services --> MCDM["Decision methods"]
    Services --> Data["Data adapters"]
    Data --> Domain