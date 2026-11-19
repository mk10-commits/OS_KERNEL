# Thread Model Explorer — Project Guide

This guide explains the simulator's terms, settings, metrics, phase modes, and classifier in plain language.

## Start the app

Double-click `start_thread_model_explorer.bat`, or run it from PowerShell:

```powershell
.\start_thread_model_explorer.bat
```

It starts the local Python web server and opens `http://127.0.0.1:8000/` in your browser. To run the command-line version instead:

```powershell
python thread_simulator.py --phase 1
python thread_simulator.py --phase 2
python thread_simulator.py --phase all
```

## The two thread models

**User-level thread (ULT):** A program's runtime manages and switches between its own threads. This simulation uses one underlying execution context for all ULTs. Switching is configured to be relatively cheap, but a blocking I/O call stalls the shared context. That means every ULT waits while the process is blocked. This is a simplified many-to-one ULT model.

**Kernel-level thread (KLT):** The operating system manages each thread as a schedulable entity. This simulation lets a waiting KLT block independently; other ready KLTs can run. It also allows KLTs to execute on multiple configured cores. This is a simplified one-to-one KLT model.

These are teaching models. Some real runtimes use M:N scheduling, fibers, asynchronous I/O, or other designs that combine features of both.

## Workload terms

A **job** is one simulated thread's work. A job consists of **CPU bursts** and, for I/O workloads, **I/O bursts**.

- A **CPU burst** is a stretch of work that needs processor time.
- An **I/O burst** is a simulated wait for an operation such as a disk or network request. While waiting, that job cannot use a CPU.
- A **CPU-bound** workload spends most of its time needing CPU work.
- An **I/O-bound** workload spends most of its time waiting for I/O, with short CPU bursts between waits.
- A **mixed** workload has meaningful amounts of both.
- A **blocking I/O call** makes the caller wait until its I/O completes. In this simulation, it blocks all work in the one-context ULT model, but only that individual thread in KLT.

All built-in jobs arrive at tick zero. Their burst lengths are fixed, so a run with the same settings is repeatable.

## Run controls

- **Project phase:** `Phase 1` displays the baseline scheduler comparison. `Phase 2` displays classification and recommendation. `Both phases` displays both outputs in order.
- **Round-robin quantum:** The maximum number of abstract CPU ticks a runnable job receives on a turn before it yields and goes to the back of the ready queue. A smaller quantum allows more frequent turns but can cause more switches.
- **ULT switch cost:** Abstract ticks charged when the ULT scheduler changes from one job to a different job on its simulated core.
- **KLT switch cost:** Abstract ticks charged when a KLT core changes from one job to another. It is set independently because kernel scheduling is modeled with a higher default overhead.
- **KLT cores:** Number of simulated KLT cores. With four cores, up to four KLT jobs may execute CPU work during the same tick. ULT remains one execution context in this baseline.

A **tick** is only a unit of simulated time. It is not a millisecond, CPU cycle, or measurement from the machine running this app.

## Phase 1 comparison metrics

- **Elapsed ticks (makespan):** Simulated time from the start until the last job completes. Lower means the workload finished sooner under these settings.
- **Mean response:** Average time from each job's arrival until it first gets CPU service. Lower means jobs start responding sooner. Because every default job arrives at time zero, response is the time until its first CPU tick.
- **Jobs / 1k ticks (throughput):** Number of completed jobs divided by elapsed time, scaled to 1,000 ticks. Higher means more jobs finish per unit of simulated time.
- **Switches:** Number of times a core changes from one previously running job to another. The initial dispatch is not counted as a context switch.
- **Switch overhead:** Total abstract ticks consumed by those context switches. The chosen switch cost is charged each time a switch occurs.
- **I/O wait ticks (thread blocked time):** Sum of all individual jobs' I/O durations. This total is identical for ULT and KLT for the same input jobs; it records how much waiting the jobs contain.
- **Idle ticks (shown as `idle` in the web view):** Ticks in which no simulated core performs CPU work. This exposes time when the ULT process-wide block leaves its only context idle. It may also include times when all jobs are waiting for I/O.
- **Effective parallelism:** Total CPU service ticks divided by elapsed ticks. A result of `1` means one core's worth of CPU work was used on average; values above `1` mean multiple cores did useful CPU work at once. It is an average, so it can be below 1 when all jobs are waiting or switch overhead consumes time.

In the command-line table, `Switches` and `Switch cost` are separate columns; `Blocked` means summed per-thread I/O wait. The web view shows I/O wait and whole-system idle together as `I/O wait · idle`.

## Phase 2 classifier and recommendation

Phase 2 has two parts:

1. **Classify the workload.** The program extracts five numeric **features** from CPU and I/O bursts:
   - `cpu_fraction`: CPU burst time divided by the total CPU plus I/O burst time.
   - `io_fraction`: I/O burst time divided by total CPU plus I/O burst time.
   - `io_bursts_per_job_scaled`: number of I/O bursts per job divided by 10. This keeps the value in a compact range for these examples.
   - `mean_cpu_burst_fraction`: average CPU burst length divided by average CPU work per job. Higher values usually indicate fewer, longer CPU bursts; lower values indicate more fragmented CPU work.
   - `cpu_work_per_job_scaled`: average CPU work per job divided by 1,000 ticks. This records the amount of CPU work as well as its proportions.

   It compares these five values with a **centroid** for each known class. A centroid is the average feature vector of the labeled examples for that class. It chooses the label with the smallest **Euclidean distance**, a straight-line distance between the workload's feature vector and a class centroid. The resulting label is `CPU-bound`, `I/O-bound`, or `Mixed`.

2. **Recommend a model.** It scores ULT and KLT using each model's Phase 1 simulation results. The lower score wins. It normalizes elapsed time, response time, switch overhead, and whole-system idle ticks against the larger ULT/KLT value for the current workload, then applies class-specific weights. It subtracts a small normalized parallelism reward. The score is a comparison value, not a duration, probability, or universal quality rating. A negative score is allowed because parallelism is subtracted.

The web view's **confidence indicator** describes the distance gap between the closest and second-closest centroids. It is not a statistically calibrated probability. A higher value means the closest centroid is farther ahead of the next choice; it does not guarantee a correct label for real traces.

## Was model training required?

There is a small training step, but no separate training setup is required from you. The program creates 240 hand-labeled synthetic examples each time Phase 2 runs: 80 CPU-bound, 80 I/O-bound, and 80 mixed. Burst counts, durations, and feature vectors vary across the dataset. It builds each class centroid from the 80 examples for that class. The generation is deterministic, so the same 240 examples and feature values recur on every run. The complete rows are in `synthetic_training_data.csv` and can be downloaded from Phase 2 in the web app.

It does **not** use an external dataset, download data, train a neural network, or require machine-learning packages. The reference patterns and their labels were chosen by the project author, so this demonstrates the classification workflow rather than claiming validated real-world accuracy. For a production classifier, representative workload traces should be collected, labeled, held out for evaluation, and used to calibrate the predictions.

## What each phase does to the output

- **Phase 1 only:** Runs the ULT/KLT baseline comparisons and shows scheduler metrics. It does not show classification or recommendations.
- **Phase 2 only:** Internally runs both schedulers because recommendation needs their outcomes, then shows features, predicted class, confidence indicator, scores, and recommendation. It hides the Phase 1 comparison table.
- **Both phases:** Shows Phase 1's baseline table first, then Phase 2's classifications and recommendations. Running both does not change the Phase 1 scheduling rules or results. The simulation is deterministic, so the baseline should match Phase 1-only output when configuration is the same.

## Important limits

The models intentionally simplify real operating systems. They omit cache effects, memory contention, locks, device queues, asynchronous I/O, scheduler policies, and operating-system details. The four-core setting is simulated capacity, not a claim about the host machine. Recommendations apply only to the supplied burst patterns, metric weights, and selected settings. Use the Phase 1 and Phase 2 reports for their detailed result tables and methodology.

## Training dataset ranges

Phase 2 creates 80 deterministic examples per class, for 240 total. All 240 feature vectors are distinct. The exact feature ranges are:

| Class | CPU fraction | I/O fraction | I/O bursts/job scaled | Mean CPU burst fraction | CPU work/job scaled |
|---|---:|---:|---:|---:|---:|
| CPU-bound | 1.0000–1.0000 | 0.0000–0.0000 | 0.0000–0.0000 | 0.2000–1.0000 | 0.1200–0.9850 |
| I/O-bound | 0.0703–0.1700 | 0.8300–0.9297 | 0.2000–1.2000 | 0.0833–0.5000 | 0.0070–0.1020 |
| Mixed | 0.4805–0.8043 | 0.1957–0.5195 | 0.2000–0.6000 | 0.1667–0.5000 | 0.0570–0.3470 |

The exact sequence of CPU and I/O burst values and the extracted features for all 240 rows are available in `synthetic_training_data.csv`. Phase 2 also reports the ranges in the console and web interface.
