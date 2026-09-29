# WAMCES: European Power System for Wide-Area Monitoring and Control

**A dynamic model of the Continental European power system built for wide-area monitoring and control studies, converted to RAMSES format.**

This repository holds the WAMCES model of Musca, Ippolito and Riva Sanseverino (University of Palermo), prepared for use with the [STEPSS](https://stepss.sps-lab.org/) power system simulation platform (RAMSES dynamic simulator, HELIOS power flow and the stepss Python API). The model is published as MATLAB/Simulink; the RAMSES data files here are converted from it, and the original archives are kept unmodified in `original-data/` as the provenance record.

The system has 3809 buses across 25 country codes at 380, 220, 132 and 750 kV, 7343 branches, 618 synchronous machines with 1854 controllers (an AVR, a PSS and a turbine/governor each), 300 grid-forming and 500 grid-following converters, and 1573 phasor measurement units, one at every bus above 230 kV. The base is 100 MVA at 50 Hz.

What distinguishes it from other European models is that the measurement and control layer is modelled explicitly: the PMUs are represented by their phase-locked loops rather than as ideal sensors, communication latencies are second-order Pade approximants, and the grid-forming converters double as the actuators of a wide-area damping control that feeds back the average of all PMU frequencies. The authors validate it against the ENTSO-E initial dynamic model under a 1000 MW imbalance in Western Europe, recovering the West to East inter-area mode at about 0.13 Hz.

## Contents

| Path | Description |
|------|-------------|
| `wamces_lf.dat` | The network: buses with their loads, lines, transformers, generators and the slack. Read by both engines |
| `wamces_lfres.dat` | The operating point, as `LFRESV` records taken from the published power flow solution. This is what initialises a RAMSES run |
| `wamces_dyn.dat` | Dynamic data only: 618 `SYNC_MACH` with their exciter, stabiliser and governor, plus 300 `GFOR`, 500 `GFOL` and 1573 `PMU` injectors. Loaded together with the two files above |
| `wamces_voltrat.dat` | Solved voltages as HELIOS writes them, kept for comparison against `wamces_lfres.dat` |
| `wamces_settings.dat` | Solver settings. Uses `$OMEGA_REF COI`, which the PMU model needs for its reference-frame observables |
| `wamces_obs.dat` | Observables selection (`SYNC *` and `INJEC *`) |
| `wamces_flat.dst` | No-disturbance scenario, used to check that the case initialises and stays still |
| `wamces_dist.dat` | The disturbance load for the power-imbalance case: a constant-impedance injector at `ES2178`, the bus the upstream script perturbs, starting at zero power |
| `wamces_step.dst` | The paper's 1000 MW power-imbalance scenario, stepping that load at t = 1 s and running to 51 s |
| `wamces_dyn_sm.dat` | `wamces_dyn.dat` with every `INJEC` record removed: the 618 machines and their controllers only. The disturbance case runs on this file, because the full plant does not yet finish it (see Status) |
| `wamces_cmd.txt`, `wamces_cmd_step.txt`, `wamces_cmd_step_sm.txt` | RAMSES command files for the flat run, and for the step with the full plant and with the machines only |
| `tools/wamces_to_ramses.py` | Regenerates every `.dat` file above from the published tables. Each conversion decision is documented in its docstrings |
| `tools/bench_machine.py` | Two-bus bench carrying the same machine, exciter and governor records, for checking the device mapping without the full network or a licence |
| `original-data/` | The published model as distributed: the MATLAB/Simulink archive and the CSV export of its nine data tables |
| `doc/` | `electricity-07-00028.pdf`, the paper describing the model |

`license.dat`, the extracted `model/` and `original-data/csv/` folders, and all simulation outputs are git-ignored.

## Quick Start

The network exceeds the 1000-bus limit of free RAMSES builds, so a dynamic run needs a full licence. Put the `$LICENSE` record in `license.dat`, which is git-ignored, and add it as an extra data file. HELIOS has no bus limit, so the power flow half runs without one.

With [stepss](https://stepss.sps-lab.org/python/):

```python
import stepss
case = stepss.cfg()
case.addData('wamces_lf.dat')
case.addData('wamces_lfres.dat')
case.addData('wamces_dyn.dat')
case.addData('wamces_settings.dat')
case.addData('license.dat')
case.addDst('wamces_flat.dst')
case.addObs('wamces_obs.dat')
case.addTrj('wamces_flat.trj')
stepss.sim().execSim(case)
```

Or run the RAMSES executable directly with `ramses -t wamces_cmd.txt`. Run from this folder so the relative paths resolve.

The power flow alone, which needs no licence:

```python
from stepss.helios import HeliosSession
pf = HeliosSession()
pf.load_file('wamces_lf.dat')
assert pf.solve()
pf.write_voltrat('wamces_voltrat.dat')
pf.close()
```

## Regenerating the data files

```sh
unzip original-data/raw_csv_data.zip -d original-data/csv
unzip original-data/wamces_model.zip -d model
python3 tools/wamces_to_ramses.py
```

The converter reads the CSV tables and the power flow solution from the MATLAB archive, and rewrites `wamces_lf.dat`, `wamces_lfres.dat` and `wamces_dyn.dat`; `wamces_dyn_sm.dat` is `wamces_dyn.dat` with the `INJEC` records removed, and `wamces_dist.dat` is written by hand. It never modifies `original-data/`.

## Status

**Runs.** The full system initialises and simulates. A 20 s no-disturbance run takes about 7 s, and every device sits still, which is the check that the conversion is self-consistent: worst relative drift is 2.6e-11 across the 618 machines, and below 1.3e-14 across all 2373 converters and PMUs.

The conversion is validated against the source model in four independent ways:

- the admittance matrix rebuilt from `wamces_lf.dat` matches the MATLAB one to 3.9e-10 relative, with an identical sparsity pattern;
- HELIOS solving the network from cold reproduces the published operating point to 7.4e-5 pu in magnitude and 0.013 degrees in angle;
- feeding `wamces_lfres.dat` back as input converges in one Newton iteration, the round-trip property that says the data and its voltages belong together;
- the 39 machines the upstream script silently up-rates are reproduced with the same indices and the same loading figures.

**The power-imbalance case runs on the machines alone.** `wamces_cmd_step_sm.txt` steps 1000 MW at the Spanish bus the upstream script perturbs and runs 51 s in about 19 s. Against the MATLAB reference it reproduces the West to East inter-area mode at 0.14 Hz to within 0.2 mHz, the roughly 0.13 Hz mode the paper reports. With the full plant (`wamces_cmd_step.txt`) the case initialises and sits still, but on the step the grid-following converters chatter on a limiter and the run does not finish; this is a solver-robustness defect tracked as [stepss-ramses issue #17](https://github.com/SPS-L/stepss-ramses/issues/17), and `CLAUDE.md` records the diagnosis.

**Requires RAMSES 3.82 or newer.** Earlier engines stop while reading the network and report the 1000-bus limit whatever licence is present, and they cannot hold this system's Jacobian.

Verified against **stepss 3.82** (RAMSES 3.82, HELIOS 1.4.1) on Linux. The upstream MATLAB model was re-run under R2026a Update 5 to confirm it still loads, compiles and simulates.

Every device uses a registered model from the standard library, so nothing here needs a custom engine build. Two approximations remain, both in the converters and both recorded in `CLAUDE.md`: the grid-following converter's PI phase-locked loop is reduced to the single first-order response time the library model exposes, and neither converter model carries the voltage-loop gains of the original. The grid-forming converter's swing dynamics transfer exactly.

### Not yet converted

The wide-area control layer is not part of these data files. The model as published runs open-loop, because the upstream script zeroes the control gain, so what is here reproduces that base case. The communication latencies and the central unit belong to the control layer and are intended to be driven from the Python interface, reading the PMU frequency observables and modulating the grid-forming converters, which is where the original applies them.

## Documentation

The data formats are documented in the STEPSS user guide at [stepss.sps-lab.org](https://stepss.sps-lab.org/). The model itself is described in the paper included as `doc/electricity-07-00028.pdf`. `CLAUDE.md` records the conversion decisions, the device mapping, and the properties of the source data that are not obvious from either.

## Data source and citation

The model is published by its authors on Zenodo and described in an open-access paper. Please cite both if you use it:

> R. Musca, M. G. Ippolito and E. Riva Sanseverino, "Dynamic Model of the European Power System for Wide-Area Monitoring and Control Applications," *Electricity*, vol. 7, no. 2, art. 28, 2026. [https://doi.org/10.3390/electricity7020028](https://doi.org/10.3390/electricity7020028)

- Paper: [https://www.mdpi.com/3822552](https://www.mdpi.com/3822552)
- Model data: [https://zenodo.org/records/18721887](https://zenodo.org/records/18721887)

## License

The model data is the work of its authors at the University of Palermo and is distributed under the Creative Commons Attribution licence (CC BY) through the paper and the Zenodo record. **This folder therefore carries no `LICENSE` file of its own**, unlike the test systems authored by SPS-L: relicensing third-party data would assert rights SPS-L does not hold. The archives in `original-data/` are unmodified, and the converted data files derived from them carry the same attribution.

## Authors

Original model by Rossano Musca, Mariano Giuseppe Ippolito and Eleonora Riva Sanseverino, Engineering Department, University of Palermo.

RAMSES conversion maintained by the [Sustainable Power Systems Laboratory (SPS-L)](https://sps-lab.org/) at the Cyprus University of Technology, under the direction of Dr. Petros Aristidou.
