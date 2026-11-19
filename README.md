# Thread Model Explorer

An educational simulator comparing user-level and kernel-level thread scheduling, with workload classification and model recommendations.

## Start the web app

Double-click `start_thread_model_explorer.bat`, or run it in PowerShell from this folder. It opens the frontend at <http://127.0.0.1:8000/>. Close the server console window (or press Ctrl+C) to stop it.

For the detailed plain-language explanation, read [PROJECT_GUIDE.md](PROJECT_GUIDE.md). For every implementation parameter and formula, see [PARAMETER_REFERENCE.md](PARAMETER_REFERENCE.md). The web page also has an expandable Concept guide.

Phase 2 uses 240 deterministic synthetic training examples (80 per class). Download them from the Phase 2 panel or inspect [synthetic_training_data.csv](synthetic_training_data.csv).

## Run phases independently from PowerShell

```powershell
python thread_simulator.py --phase 1
python thread_simulator.py --phase 2
python thread_simulator.py --phase all
```

- `--phase 1` runs the baseline scheduler comparison only.
- `--phase 2` shows classification and recommendations only; it internally simulates both models to get metrics for its recommendation.
- `--phase all` displays both phases in order. The default is `all`.

Add `--json` for machine-readable output. Tuning options are `--quantum`, `--ult-switch`, `--klt-switch`, and `--cores`:

```powershell
python thread_simulator.py --phase all --quantum 5 --cores 8
```

## Requirements

Python 3.10 or newer. No third-party packages are needed.

## Reports

- [Phase 1 report](reports/phase1_report.md)
- [Phase 2 report](reports/phase2_report.md)

