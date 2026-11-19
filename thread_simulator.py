"""Deterministic educational simulator for ULT and KLT scheduling models."""
from __future__ import annotations

import argparse
import csv
import io
import json
from collections import deque
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class Burst:
    kind: str  # "cpu" or "io"
    duration: int

@dataclass
class Job:
    name: str
    bursts: list[Burst]
    arrival: int = 0
    index: int = 0
    remaining: int = 0
    state: str = "new"
    io_until: int = 0
    first_run: int | None = None
    completion: int | None = None
    cpu_ticks: int = 0
    blocked_ticks: int = 0

    def __post_init__(self) -> None:
        if self.bursts:
            self.remaining = self.bursts[0].duration

@dataclass
class Core:
    job: Job | None = None
    quantum_left: int = 0
    last_job: str | None = None
    switch_left: int = 0

@dataclass
class Scenario:
    name: str
    description: str
    jobs: list[Job]

def make_jobs(kind: str, count: int = 4) -> list[Job]:
    jobs = []
    for i in range(count):
        if kind == "cpu-bound":
            bursts = [Burst("cpu", 320 + i * 20)]
        elif kind == "io-bound":
            bursts = [part for _ in range(5) for part in (Burst("cpu", 8 + i % 3), Burst("io", 30 + i * 2))]
            bursts.append(Burst("cpu", 5))
        else:
            bursts = [Burst("cpu", 45 + i * 4), Burst("io", 25 + i * 2), Burst("cpu", 70 + i * 5), Burst("io", 15 + i), Burst("cpu", 30)]
        jobs.append(Job(f"J{i+1}", bursts))
    return jobs

def scenarios() -> list[Scenario]:
    return [Scenario(n, d, make_jobs(n)) for n, d in [
        ("cpu-bound", "Long CPU bursts with no I/O waits"),
        ("io-bound", "Short CPU bursts interleaved with blocking I/O"),
        ("mixed", "CPU bursts and blocking I/O of varied lengths"),
    ]]

def run(jobs_in: list[Job], model: str, quantum: int, switch_cost: int, cores_count: int, io_blocks_process: bool, max_ticks: int = 1_000_000) -> dict[str, Any]:
    # Clone mutable jobs so each scheduler sees identical workload definitions.
    jobs = [Job(j.name, list(j.bursts), j.arrival) for j in jobs_in]
    ready: deque[Job] = deque()
    cores = [Core() for _ in range(1 if model == "ULT" else cores_count)]
    now = 0
    switches = 0
    switch_ticks = 0
    cpu_busy_ticks = 0
    process_block_until = 0
    timeline: list[list[str | None]] = []

    while any(j.state != "done" for j in jobs):
        if now >= max_ticks:
            raise RuntimeError("Simulation limit exceeded; check workload durations.")
        for j in jobs:
            if j.state == "new" and j.arrival <= now:
                j.state = "ready"
                ready.append(j)
            if j.state == "io" and j.io_until <= now:
                j.index += 1
                if j.index >= len(j.bursts):
                    j.state = "done"
                    j.completion = now
                else:
                    j.remaining = j.bursts[j.index].duration
                    j.state = "ready"
                    ready.append(j)
        # A blocking syscall in a many-to-one ULT model stops the sole process context.
        process_blocked = model == "ULT" and io_blocks_process and now < process_block_until
        row: list[str | None] = []
        for core in cores:
            current = core.job
            if current is not None and current.state != "running":
                core.job = None
                current = None
            if current is not None and core.quantum_left <= 0:
                current.state = "ready"
                ready.append(current)
                core.job = None
                current = None
            if current is None and ready and not process_blocked:
                picked = ready.popleft()
                if picked.state == "ready":
                    picked.state = "running"
                    core.job = picked
                    core.quantum_left = quantum
                    current = picked
            if current is None or process_blocked:
                row.append(None)
                continue
            if core.last_job != current.name:
                if core.last_job is not None:
                    switches += 1
                    core.switch_left = switch_cost
                core.last_job = current.name
            if core.switch_left > 0:
                core.switch_left -= 1
                switch_ticks += 1
                row.append(f"{current.name}(switch)")
                continue
            if current.first_run is None:
                current.first_run = now
            current.remaining -= 1
            current.cpu_ticks += 1
            cpu_busy_ticks += 1
            core.quantum_left -= 1
            row.append(current.name)
            if current.remaining == 0:
                current.index += 1
                if current.index >= len(current.bursts):
                    current.state = "done"
                    current.completion = now + 1
                else:
                    nxt = current.bursts[current.index]
                    current.remaining = nxt.duration
                    if nxt.kind == "io":
                        current.state = "io"
                        current.io_until = now + 1 + nxt.duration
                        current.blocked_ticks += nxt.duration
                        if model == "ULT" and io_blocks_process:
                            process_block_until = current.io_until
                    else:
                        # CPU bursts separated by no I/O continue as the same logical thread.
                        current.state = "ready"
                        ready.append(current)
                core.job = None
        timeline.append(row)
        now += 1

    makespan = max((j.completion or 0) for j in jobs) - min((j.arrival for j in jobs), default=0)
    makespan = max(1, makespan)
    responses = [(j.first_run - j.arrival) for j in jobs if j.first_run is not None]
    return {
        "model": model,
        "jobs": len(jobs),
        "makespan_ticks": makespan,
        "mean_response_ticks": round(sum(responses) / len(responses), 2) if responses else None,
        "throughput_jobs_per_1000_ticks": round(len(jobs) * 1000 / makespan, 3),
        "context_switches": switches,
        "switch_overhead_ticks": switch_ticks,
        "blocked_thread_ticks": sum(j.blocked_ticks for j in jobs),
        "elapsed_blocked_ticks": sum(1 for row in timeline if all(x is None for x in row)),
        "cpu_service_ticks": cpu_busy_ticks,
        "effective_parallelism": round(cpu_busy_ticks / makespan, 3),
        "configured_cores": len(cores),
        "per_job": [{"job": j.name, "response_ticks": (j.first_run - j.arrival) if j.first_run is not None else None, "completion_ticks": j.completion, "cpu_ticks": j.cpu_ticks, "blocked_ticks": j.blocked_ticks} for j in jobs],
    }

def compare(quantum: int = 10, ult_switch: int = 1, klt_switch: int = 2, cores: int = 4) -> dict[str, Any]:
    output = {"configuration": {"quantum_ticks": quantum, "ult_switch_cost_ticks": ult_switch, "klt_switch_cost_ticks": klt_switch, "klt_cores": cores}, "scenarios": []}
    for scenario in scenarios():
        out = {"scenario": scenario.name, "description": scenario.description, "results": [
            run(scenario.jobs, "ULT", quantum, ult_switch, 1, True),
            run(scenario.jobs, "KLT", quantum, klt_switch, cores, False),
        ]}
        output["scenarios"].append(out)
    return output

FEATURE_NAMES = ("cpu_fraction", "io_fraction", "io_bursts_per_job_scaled", "mean_cpu_burst_fraction", "cpu_work_per_job_scaled")

def extract_features(jobs: list[Job]) -> dict[str, float]:
    cpu_total = sum(b.duration for j in jobs for b in j.bursts if b.kind == "cpu")
    io_total = sum(b.duration for j in jobs for b in j.bursts if b.kind == "io")
    io_count = sum(1 for j in jobs for b in j.bursts if b.kind == "io")
    cpu_bursts = [b.duration for j in jobs for b in j.bursts if b.kind == "cpu"]
    cpu_per_job = cpu_total / max(1, len(jobs))
    total = max(1, cpu_total + io_total)
    return {
        "cpu_fraction": round(cpu_total / total, 4),
        "io_fraction": round(io_total / total, 4),
        "io_bursts_per_job_scaled": round((io_count / max(1, len(jobs))) / 10, 4),
        "mean_cpu_burst_fraction": round((sum(cpu_bursts) / max(1, len(cpu_bursts))) / max(1, cpu_total / max(1, len(jobs))), 4),
        "cpu_work_per_job_scaled": round(cpu_per_job / 1000, 4),
    }

def training_examples() -> list[tuple[str, list[Job]]]:
    """Create 240 deterministic synthetic examples, with 80 examples per class."""
    examples: list[tuple[str, list[Job]]] = []
    for i in range(80):
        # CPU-only examples vary total service and how many CPU bursts divide the work.
        total_cpu = 120 + (i * 37 % 881)
        burst_count = 1 + (i % 5)
        base, remainder = divmod(total_cpu, burst_count)
        cpu_bursts = [Burst("cpu", base + (1 if part < remainder else 0)) for part in range(burst_count)]
        examples.append(("CPU-bound", [Job(f"cpu-{i+1:03d}", cpu_bursts)]))

        # Each I/O example has 2-12 cycles, short CPU work, and substantially longer waits.
        cycles = 2 + (i % 11)
        io_bursts: list[Burst] = []
        for cycle in range(cycles):
            cpu_time = 2 + (i * 7 + cycle * 3) % 12
            io_time = 25 + (i * 13 + cycle * 7) % 76
            io_bursts.extend((Burst("cpu", cpu_time), Burst("io", io_time)))
        examples.append(("I/O-bound", [Job(f"io-{i+1:03d}", io_bursts)]))

        # Mixed examples vary from 2-6 CPU/I/O pairs, with both phases having meaningful duration.
        mixed_cycles = 2 + (i % 5)
        mixed_bursts: list[Burst] = []
        for cycle in range(mixed_cycles):
            cpu_time = 25 + (i * 11 + cycle * 7) % 56
            io_time = 8 + (i * 17 + cycle * 9) % 42
            mixed_bursts.extend((Burst("cpu", cpu_time), Burst("io", io_time)))
        examples.append(("Mixed", [Job(f"mixed-{i+1:03d}", mixed_bursts)]))
    return examples

def training_dataset_summary() -> dict[str, Any]:
    examples = training_examples()
    by_label: dict[str, list[dict[str, float]]] = {}
    for label, jobs in examples:
        by_label.setdefault(label, []).append(extract_features(jobs))
    ranges = {}
    for label, rows in by_label.items():
        ranges[label] = {name: {"min": round(min(row[name] for row in rows), 4),
                               "max": round(max(row[name] for row in rows), 4)} for name in FEATURE_NAMES}
    return {"sample_count": len(examples), "samples_per_class": {label: len(rows) for label, rows in by_label.items()},
            "feature_ranges": ranges, "source": "Deterministic generated synthetic examples; no random values"}

def training_dataset_csv() -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["sample_id", "class_label", "burst_sequence", *FEATURE_NAMES])
    for label, jobs in training_examples():
        job = jobs[0]
        sequence = "; ".join(f"{burst.kind.upper()}:{burst.duration}" for burst in job.bursts)
        features = extract_features(jobs)
        writer.writerow([job.name, label, sequence, *(features[name] for name in FEATURE_NAMES)])
    return output.getvalue()

def train_centroids() -> dict[str, list[float]]:
    grouped: dict[str, list[list[float]]] = {}
    for label, jobs in training_examples():
        f = extract_features(jobs)
        grouped.setdefault(label, []).append([f[name] for name in FEATURE_NAMES])
    return {label: [sum(row[i] for row in rows) / len(rows) for i in range(len(FEATURE_NAMES))] for label, rows in grouped.items()}

def classify_workload(jobs: list[Job]) -> dict[str, Any]:
    features = extract_features(jobs)
    vector = [features[name] for name in FEATURE_NAMES]
    centroids = train_centroids()
    distances = {label: sum((vector[i] - center[i]) ** 2 for i in range(len(vector))) ** 0.5 for label, center in centroids.items()}
    ranked = sorted(distances.items(), key=lambda item: item[1])
    best_label, best_distance = ranked[0]
    second_distance = ranked[1][1]
    confidence = 1.0 - best_distance / max(1e-9, best_distance + second_distance)
    return {"classification": best_label, "confidence": round(confidence, 3), "features": features,
            "distances": {label: round(distance, 4) for label, distance in distances.items()},
            "method": "nearest centroid (Euclidean distance), trained on deterministic labeled burst-pattern examples"}

def recommend_model(classification: dict[str, Any], result_pair: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare both measured simulator outcomes with a transparent composite cost."""
    # Normalize latency-related measures to avoid making a large tick count dominate by scale alone.
    max_elapsed = max(1, max(r["makespan_ticks"] for r in result_pair))
    max_response = max(1, max(r["mean_response_ticks"] for r in result_pair))
    max_switch = max(1, max(r["switch_overhead_ticks"] for r in result_pair))
    max_idle = max(1, max(r["elapsed_blocked_ticks"] for r in result_pair))
    weights = {"CPU-bound": (0.40, 0.15, 0.10, 0.05), "I/O-bound": (0.35, 0.20, 0.10, 0.25), "Mixed": (0.40, 0.20, 0.10, 0.15)}[classification["classification"]]
    scores = {}
    for result in result_pair:
        elapsed, response, switch, idle = weights
        score = (elapsed * result["makespan_ticks"] / max_elapsed +
                 response * (result["mean_response_ticks"] or 0) / max_response +
                 switch * result["switch_overhead_ticks"] / max_switch +
                 idle * result["elapsed_blocked_ticks"] / max_idle -
                 0.15 * result["effective_parallelism"] / max(1, result["configured_cores"]))
        scores[result["model"]] = round(score, 4)
    choice = min(scores, key=scores.get)
    reasons = {
        "CPU-bound": "CPU-heavy work benefits from multicore execution; the score also accounts for elapsed time, response, and switch overhead.",
        "I/O-bound": "For blocking I/O, independent KLT blocking can keep other jobs runnable; the score includes whole-system idle time.",
        "Mixed": "The workload combines CPU and I/O phases, so the recommendation balances elapsed time, response, switch overhead, idle time, and parallelism.",
    }
    return {"recommended_model": choice, "scores_lower_is_better": scores, "rationale": reasons[classification["classification"]],
            "basis": "Composite of normalized simulated elapsed time, response time, switch overhead, whole-system idle time, and effective parallelism. This is a simulator-specific recommendation."}

def phase2(quantum: int, ult_switch: int, klt_switch: int, cores: int) -> dict[str, Any]:
    baseline = compare(quantum, ult_switch, klt_switch, cores)
    scenarios_by_name = {s.name: s for s in scenarios()}
    results = []
    for scenario_result in baseline["scenarios"]:
        name = scenario_result["scenario"]
        classification = classify_workload(scenarios_by_name[name].jobs)
        recommendation = recommend_model(classification, scenario_result["results"])
        results.append({"scenario": name, "classification": classification, "baseline_metrics": scenario_result["results"], "recommendation": recommendation})
    return {"configuration": baseline["configuration"], "classifier": "nearest-centroid classifier over CPU/IO fractions, I/O burst frequency, CPU burst fragmentation, and scaled CPU work", "training_data": training_dataset_summary(), "results": results}

def print_phase2(data: dict[str, Any]) -> None:
    print("PHASE 2 - Workload classification and model recommendation")
    training = data["training_data"]
    distribution = ", ".join(f"{label}: {count}" for label, count in training["samples_per_class"].items())
    print(f"Classifier: nearest-centroid over {training['sample_count']} deterministic synthetic examples ({distribution}).")
    print("Feature ranges (min..max):")
    for label, ranges in training["feature_ranges"].items():
        parts = [f"{name} {values['min']}..{values['max']}" for name, values in ranges.items()]
        print(f"  {label}: " + ", ".join(parts))
    print()
    print(f"{'Workload':<12} {'Class':<12} {'Confidence':>10} {'ULT score':>11} {'KLT score':>11} {'Recommend':>12}")
    print("-" * 72)
    for item in data["results"]:
        c, r = item["classification"], item["recommendation"]
        scores = r["scores_lower_is_better"]
        print(f"{item['scenario']:<12} {c['classification']:<12} {c['confidence']:>10.3f} {scores['ULT']:>11.4f} {scores['KLT']:>11.4f} {r['recommended_model']:>12}")
        print(f"  features={c['features']}")
        print(f"  rationale: {r['rationale']}")

def print_table(data: dict[str, Any]) -> None:
    print("PHASE 1 - Baseline thread-model simulation (abstract ticks; deterministic)")
    cfg = data["configuration"]
    print(f"quantum={cfg['quantum_ticks']} | ULT switch={cfg['ult_switch_cost_ticks']} | KLT switch={cfg['klt_switch_cost_ticks']} | KLT cores={cfg['klt_cores']}\n")
    print(f"{'Scenario':<12} {'Model':<5} {'Elapsed':>8} {'Response':>9} {'Jobs/1k':>9} {'Switches':>9} {'Switch cost':>12} {'Blocked':>9} {'Parallel':>9}")
    print("-" * 96)
    for s in data["scenarios"]:
        for r in s["results"]:
            print(f"{s['scenario']:<12} {r['model']:<5} {r['makespan_ticks']:>8} {r['mean_response_ticks']:>9} {r['throughput_jobs_per_1000_ticks']:>9} {r['context_switches']:>9} {r['switch_overhead_ticks']:>12} {r['blocked_thread_ticks']:>9} {r['effective_parallelism']:>9}")
    print("\nNotes: ULT uses one simulated execution context and process-wide blocking for blocking I/O. KLT uses independent blocking and configured cores. Metrics are model outputs, not host benchmarks.")

def main() -> None:
    parser = argparse.ArgumentParser(description="Compare simulated user-level and kernel-level thread schedulers.")
    parser.add_argument("--phase", choices=("1", "2", "all"), default="all", help="Run Phase 1 only, Phase 2 only, or both (default)")
    parser.add_argument("--quantum", type=int, default=10, help="Round-robin quantum in abstract ticks")
    parser.add_argument("--ult-switch", type=int, default=1, help="ULT context-switch overhead in ticks")
    parser.add_argument("--klt-switch", type=int, default=2, help="KLT context-switch overhead in ticks")
    parser.add_argument("--cores", type=int, default=4, help="Simulated KLT cores")
    parser.add_argument("--json", action="store_true", help="Print full results as JSON")
    args = parser.parse_args()
    if min(args.quantum, args.cores) <= 0 or min(args.ult_switch, args.klt_switch) < 0:
        parser.error("quantum and cores must be positive; switch costs cannot be negative")
    phase1_data = compare(args.quantum, args.ult_switch, args.klt_switch, args.cores) if args.phase in ("1", "all") else None
    phase2_data = phase2(args.quantum, args.ult_switch, args.klt_switch, args.cores) if args.phase in ("2", "all") else None
    if args.json:
        payload = phase1_data if args.phase == "1" else phase2_data if args.phase == "2" else {"phase1": phase1_data, "phase2": phase2_data}
        print(json.dumps(payload, indent=2))
    else:
        if phase1_data is not None:
            print_table(phase1_data)
            if phase2_data is not None:
                print("\n" + "=" * 72 + "\n")
        if phase2_data is not None:
            print_phase2(phase2_data)

if __name__ == "__main__":
    main()
