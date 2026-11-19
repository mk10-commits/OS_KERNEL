# Thread Model Explorer — Parameter Reference

This document describes the user controls, command-line/API values, built-in workload inputs, classifier features, scoring weights, and output fields used by the implementation. All time values are **abstract simulation ticks**, not milliseconds or measurements of the host computer.

## 1. Parameters you can change

| Parameter | Default | Allowed values | What it changes |
|---|---:|---|---|
| Phase (`--phase`, web selector) | `all` | `1`, `2`, `all` | `1` displays the baseline comparison. `2` displays classification and recommendation (it still simulates both models internally). `all` displays both. |
| Round-robin quantum (`--quantum`) | 10 ticks | Positive integer | Maximum CPU ticks a job can use on a turn before the scheduler moves it to the back of the ready queue. Shorter quanta can improve turn-taking but may increase switches. |
| ULT switch cost (`--ult-switch`) | 1 tick | Integer >= 0 | Number of ticks charged when the ULT execution context switches from one job to another. |
| KLT switch cost (`--klt-switch`) | 2 ticks | Integer >= 0 | Number of ticks charged on a KLT core when it changes from one previously running job to another. |
| KLT cores (`--cores`) | 4 | Positive integer | Number of simulated KLT cores. Up to this many KLT jobs can do CPU work in one tick. ULT always uses one simulated execution context in this model. |
| JSON (`--json`) | Off | Flag | Prints machine-readable results instead of the text tables. |

The web form uses the same values. It sends `phase`, `quantum`, `ult_switch`, `klt_switch`, and `cores` to `/api/run`. The web server binds to `127.0.0.1:8000`; API inputs must use an allowed phase, positive quantum/core count, and nonnegative switch costs. Requests over 4,096 bytes are rejected.

## 2. Built-in Phase 1 workloads

There are four jobs per workload (`J1` through `J4`). All arrive at tick zero. In the formulas below, `i` is zero-based: `J1` uses `i=0`, `J2` uses `i=1`, and so on.

| Workload | CPU/I/O burst sequence for job `i` |
|---|---|
| CPU-bound | One CPU burst of `320 + 20*i` ticks. |
| I/O-bound | Five repetitions of CPU `8 + (i mod 3)` ticks, then I/O `30 + 2*i` ticks; finish with a CPU burst of 5 ticks. |
| Mixed | CPU `45 + 4*i`, I/O `25 + 2*i`, CPU `70 + 5*i`, I/O `15 + i`, CPU 30 ticks. |

A **CPU burst** consumes processor service. An **I/O burst** waits without consuming CPU. The workload input and tick unit are the same for both models.

## 3. Scheduler and job parameters inside the simulator

The `run(...)` function accepts:

- `jobs_in`: workload jobs and their burst lists.
- `model`: `ULT` or `KLT`.
- `quantum`: round-robin CPU ticks per turn.
- `switch_cost`: ticks charged on a change to another job.
- `cores_count`: number of KLT cores; ULT is forced to one core.
- `io_blocks_process`: whether a blocking I/O call pauses the entire ULT process. It is true for ULT and false for KLT.
- `max_ticks`: safety limit of 1,000,000 simulated ticks; exceeding it stops the run with an error.

Jobs use these state values: `new` (not yet arrived), `ready` (waiting for CPU), `running` (on a simulated core), `io` (waiting for I/O), and `done` (finished). The ready queue is first-in, first-out. A CPU tick is executed once per active core per scheduler step. An initial dispatch is not counted as a context switch; changing from the core's previous job is counted. Switch overhead pauses CPU work for the configured number of ticks.

Each job stores its burst `index`, remaining burst time, I/O completion time, first CPU time, completion time, CPU service ticks, and I/O blocked ticks. Each core stores its current job, remaining quantum, last job, and remaining switch overhead.

## 4. Phase 1 output fields

| Output field | Meaning / calculation |
|---|---|
| `makespan_ticks` / Elapsed | Last completion time minus earliest arrival, at least 1 tick. |
| `mean_response_ticks` / Response | Average over jobs of first CPU service time minus arrival time. |
| `throughput_jobs_per_1000_ticks` / Jobs/1k | `job_count * 1000 / makespan_ticks`. |
| `context_switches` / Switches | Number of core changes from one previous job to a different job. Initial dispatch is excluded. |
| `switch_overhead_ticks` / Switch cost | Total ticks consumed by the configured switch delays. |
| `blocked_thread_ticks` / I/O wait | Sum of each job's I/O wait durations. |
| `elapsed_blocked_ticks` / Idle | Number of timeline ticks where no core performed CPU or switch work. Includes periods where all jobs are waiting; in ULT it also reflects the process-wide block. |
| `cpu_service_ticks` | Total CPU burst ticks actually executed. |
| `effective_parallelism` / Parallel | `cpu_service_ticks / makespan_ticks`; can exceed 1 when several cores execute at once. |
| `per_job` | Per-job response, completion, CPU service, and I/O wait values. |

## 5. Phase 2 feature parameters

Features are extracted from the burst definitions and rounded to four decimal places before classification:

| Feature | Calculation | Plain meaning |
|---|---|---|
| `cpu_fraction` | Total CPU burst ticks / (total CPU + I/O burst ticks) | Share of listed burst time spent needing CPU. |
| `io_fraction` | Total I/O burst ticks / (total CPU + I/O burst ticks) | Share of listed burst time spent waiting for I/O. |
| `io_bursts_per_job_scaled` | (I/O burst count / job count) / 10 | I/O burst frequency, scaled down by 10. |
| `mean_cpu_burst_fraction` | (Average CPU burst length) / (CPU ticks per job) | How fragmented CPU work is; more CPU bursts generally give a smaller value. |
| `cpu_work_per_job_scaled` | (Total CPU ticks / job count) / 1,000 | Average amount of CPU work per job, scaled down by 1,000. |

The first two features sum to approximately 1, subject to rounding. Scaling keeps feature magnitudes more comparable for the distance calculation.

## 6. Synthetic classifier dataset parameters

The program deterministically creates 240 labeled examples each time Phase 2 runs: 80 per class. `i` ranges from 0 through 79; `c` is the zero-based cycle number. These formulas generate burst durations in abstract ticks:

- **CPU-bound:** total CPU work `120 + ((37*i) mod 881)`; split it as evenly as possible across `1 + (i mod 5)` CPU bursts. No I/O bursts.
- **I/O-bound:** number of CPU/I/O pairs is `2 + (i mod 11)`. For each cycle `c`, CPU duration is `2 + ((7*i + 3*c) mod 12)` and I/O duration is `25 + ((13*i + 7*c) mod 76)`.
- **Mixed:** number of CPU/I/O pairs is `2 + (i mod 5)`. For each cycle `c`, CPU duration is `25 + ((11*i + 7*c) mod 56)` and I/O duration is `8 + ((17*i + 9*c) mod 42)`.

These fixed integer formulas contain no random sampling. The exact generated sequences and feature values are in `synthetic_training_data.csv` (240 data rows plus a header). All 240 five-feature vectors are distinct.

The classifier computes the arithmetic mean (centroid) of each class's 80 feature vectors, then measures straight-line Euclidean distance from a scenario to each centroid. The nearest centroid supplies the predicted class. Its confidence indicator is `1 - nearest_distance / (nearest_distance + second_nearest_distance)` (with a tiny denominator floor); it is a distance gap indicator, not a calibrated probability.

## 7. Recommendation-score parameters

For each scenario, ULT and KLT are scored against each other. Lower is preferred. First normalize each measure by the larger value from the two models (floor of 1): elapsed time, response time, switch overhead, and whole-system idle ticks. Then calculate:

`score = W_elapsed*(elapsed/max_elapsed) + W_response*(response/max_response) + W_switch*(switch_ticks/max_switch) + W_idle*(idle_ticks/max_idle) - 0.15*(parallelism/max(1,core_count))`

Weights `(W_elapsed, W_response, W_switch, W_idle)` depend on the predicted class:

| Predicted class | Elapsed | Response | Switch overhead | Idle time |
|---|---:|---:|---:|---:|
| CPU-bound | 0.40 | 0.15 | 0.10 | 0.05 |
| I/O-bound | 0.35 | 0.20 | 0.10 | 0.25 |
| Mixed | 0.40 | 0.20 | 0.10 | 0.15 |

The `0.15` parallelism reward is fixed. A negative score is possible because parallelism is subtracted. Scores are comparison values, not probabilities or physical units. These weights are project choices and can affect the recommendation.

## 8. Dataset CSV columns

`sample_id` uniquely names the generated example; `class_label` is its hand-assigned class; `burst_sequence` lists entries such as `CPU:120` and `IO:25`; the remaining columns contain the five extracted feature values described above.

## 9. Important interpretation

The 240 examples train the class centroids; they are not 240 separate Phase 1 performance runs. Phase 1 still compares the three built-in workload scenarios. Phase 2 classifies those three scenarios using the 240-row reference dataset and then recommends a model using their Phase 1 simulation metrics. The simulation does not measure real hardware, and its synthetic data and scoring weights are educational choices.
