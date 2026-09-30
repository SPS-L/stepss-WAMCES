# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this folder is

Upstream material for the WAMCES model: a phasor-domain dynamic model of the Continental European power system built for wide-area monitoring and control studies, by Musca, Ippolito and Riva Sanseverino at the University of Palermo. The paper is `doc/electricity-07-00028.pdf` (Electricity 2026, 7, 28, MDPI, CC BY); the data it points to is Zenodo record 18721887, mirrored here in `original-data/`.

The static network, the 618 synchronous machines with their controllers, the 300 grid-forming and 500 grid-following converters and the 1573 PMUs are all converted, and `README.md` gives the user-facing view. `PaperReplication.ipynb` reproduces the paper's simulations and is committed with its outputs; it needs stepss 3.83 and a licence. This is its own repository, `SPS-L/stepss-WAMCES`, used as a submodule of `stepss-test-systems`. The parent `CLAUDE.md` governs everything about how a test system here is laid out, run and licensed; this file covers only what is specific to this dataset.

## What is in the two archives

`original-data/wamces_model.zip` is the model as published: nine `data_*.mat` tables, `powerflow_sol.mat`, `wamces_model.slx` and the driver `wamces_script.m`. `original-data/raw_csv_data.zip` is the same nine tables exported to CSV and nothing else, so it carries no power flow and no Simulink model.

Scale, counted from the CSVs rather than from the abstract: 3809 buses across 25 country codes (380 kV 1569, 220 kV 2213, 132 kV 23, 750 kV 4), 7343 branches, 618 synchronous machines, 618 AVRs, 618 PSSs, 618 turbine/governors, 300 grid-forming converters, 500 grid-following converters, 1573 PMUs. System base 100 MVA, 50 Hz.

The `ID` column of `data_sm`, `data_avr`, `data_pss`, `data_tur`, `data_gfm`, `data_gfl` and `data_pmu` is a dense `1..N`, and the controller tables are joined to the machines **positionally**: AVR row *i*, PSS row *i* and turbine row *i* belong to machine *i*. There is no key linking them other than the row number.

## Running the upstream model

```sh
unzip original-data/wamces_model.zip -d model
```

Then in MATLAB, from `model/`, run `wamces_script.m`. It needs MATLAB with Simulink; the model was saved with R2024b Update 6 and uses a fixed-step auto solver at 10 ms over a 50 s horizon. The top level is three subsystems, `Sources` (synchronous generation with its AVR, PSS and governor/turbine blocks, plus GFM and GFL generation), `Network` (including `PMUs`) and `WAMC` (the wide-area damping controller: central unit, latency, lead-lag stages), feeding eight scopes.

The last line of the script is `sim('wamces_model.mdl')` and the archive ships `wamces_model.slx`. Expect to fix that before the first run.

## How the script uses the data, and where that bites

- **The operating point comes from `powerflow_sol.mat`, not from the bus table.** `bus_results` is a plain 3809x8 double array in per unit on 100 MVA. The `Vmag`, `Vang`, `Pgen`, `Qgen`, `Ploa` and `Qloa` columns of `data_bus` are never read: the script takes only `Type` and `Vr` from that table. Those columns are in MW/Mvar and degrees and describe a different snapshot (355,758 MW of load against the solution's 249,031 MW), so treating them as the operating point produces a case that looks plausible and is wrong.
- **The bus type column is what separates injection buses from passive ones, and it does not cover the converters.** The 618 machine buses are exactly the 5 type-1 and 613 type-2 buses, but all 800 converter buses are type 3. The script therefore starts from `Type==3` and then subtracts the converter buses before the Schur complement; without that subtraction the IBRs would be eliminated as passive nodes. The partition is 2391 passive plus 1418 injection, which is the full 3809.
- **The admittance builder reads only `ID1`, `ID2`, `R` and `X`.** Line charging `B`, `Tap` and `PhaseShift` are dropped, and the bus shunts `Gshu` and `Bshu` are never used either. In the published data all five columns are identically zero, so nothing is lost today. Change or extend the data and they will be dropped silently.
- **The script edits the data it loads.** Any machine whose power flow dispatch exceeds 80 % of its `Sr` is up-rated to `S/0.8` (printed as it happens), and `Tgfm.Kw(:) = 0` zeroes the grid-forming frequency droop gain that the table carries. Both change the physics relative to a naive read of the CSVs.
- **PMU placement is derived, not stored.** `data_pmu` has 1573 rows and its `BusID` set is exactly the set of buses with `Vr > 230`, that is every 380 kV and 750 kV bus. 543 of them sit at injection buses and 1030 at passive buses; the wide-area controller uses the two groups differently.
- **The disturbance is a conductance, not an event.** `idis = 2178`, `deltaP = 1000` MW, added to the diagonal of a second copy of the augmented admittance matrix which is then reduced in parallel with the base one. Bus 2178 is a 380 kV Spanish bus hosting machine 386 (`Sr` 1649 MVA), so the step lands on a generator bus rather than on a passive load bus.

Uniform values worth knowing before hunting for per-device data: every machine has `Ra = 0` and `D = 0`, and every converter, grid-forming and grid-following alike, has `Yf = -1.25i`.

## The conversion to RAMSES

`tools/wamces_to_ramses.py` regenerates `wamces_lf.dat` (BUS, LINE, TRANSFO, GENER, SLACK) and `wamces_lfres.dat` (the operating point) from the CSVs plus `powerflow_sol.mat`. It needs `original-data/csv/` and `model/` unpacked from the two archives; both are gitignored, so the archives stay the provenance record.

Five things the conversion has to get right, each of which was wrong or would have been wrong on the obvious reading:

- **`LINE` takes ohms, `TRANSFO` takes percent.** WAMCES is per unit on 100 MVA throughout. A line converts as `R_ohm = R_pu * Vnom^2 / 100`; a transformer is emitted on `SNOM = 100` MVA so that percent is exactly `R_pu * 100`. Worst per-element rounding error at the emitted precision is 1.3e-7.
- **`LFRESV PHASV` is in radians.** The record looks like it should be degrees and is not. HELIOS's own `write_voltrat()` output is what settles it, and the docs confirm it.
- **Branches split by voltage level.** RAMSES forbids a `LINE` between two nominal voltages, and WAMCES has one branch table with no transformer flag, so the split is derived from the end buses: 6819 lines, 524 transformers. All 524 are emitted at nominal ratio (`N = 100`, `PHI = 0`), which is exactly how the MATLAB admittance builder treats them.
- **`SLACK` names a bus, not a generator**, and there must be exactly one. The published solution holds five buses at 1.0 angle 0 (three FR, one DE, one PL, all on 5000 MVA machines), so the largest is taken as slack and the other four become ordinary voltage-imposed generators.
- **The converters are dispatched at zero.** Every GFM and GFL bus has `Pgen = Qgen = 0` in the solution, so all 254.5 GW comes from the 618 machines and only 468 of those carry load. The IBRs contribute dynamics only, which is why converter model fidelity does not affect the operating point at all.

Validation, all three currently passing:

1. The admittance matrix rebuilt from `wamces_lf.dat` matches `build_admittance_matrix` to 3.9e-10 relative, with an identical sparsity pattern.
2. HELIOS solving `wamces_lf.dat` cold reproduces the published operating point to 7.4e-5 pu in magnitude and 0.013 degrees in angle, in 5 Newton iterations.
3. Feeding `wamces_lfres.dat` back as input converges in 1 iteration with a 1.3 kW worst mismatch, which is the round-trip property the power flow documentation describes.

## The disturbance case, and how it compares

`wamces_dist.dat` plus `wamces_step.dst` reproduce the paper's power-imbalance scenario (`wamces_step_sm.cfg` runs it on `wamces_dyn_sm.dat`, the machines-only copy of `wamces_dyn.dat`; `wamces_step.cfg` on the full plant): 1000 MW switched in at `ES2178`, the bus the upstream script perturbs. Every `.dst` here applies its disturbance at **t = 1 s**, never at t = 0, so a run always has a second of initialisation to prove it is flat before anything happens. The MATLAB reference steps at t = 0, so its time axis is shifted by 1 s when comparing.

The load is a pure constant impedance (`alpha = beta = 2`), which is what the MATLAB model adds: a shunt conductance on the diagonal of the augmented admittance matrix. It starts at zero power and is stepped by `CHGPRM`, so the base operating point is untouched.

**The step changes P and Q together at 0.99 leading**, the power factor every one of the 3782 loaded buses shares exactly (`Q/P = -0.142492`). Note this is a deliberate divergence: the upstream model steps **P alone**, since a conductance has no reactive part. Comparisons against the MATLAB reference are therefore not quite like for like, and the reactive step is worth removing before drawing conclusions about small differences.

Two spellings to get right, both of which cost a run:

- The unit token in `CHGPRM` is **`MVAR`**, uppercase. The documentation writes `MVAr`, which the parser rejects with `Error in disturbance description` and no hint as to which field is wrong. `MW` is spelled as documented.
- A hand-written RAMSES command file needs **trailing blank lines** after `disc.trace`, or `setup_runtime_observables` stops with `Error reading name of display output`. The repository ships `.cfg` scenario files instead, and `stepss.cfg` writes its own command file, so this only bites when running the engine by hand.

### Agreement with the source model

Machines only, against `f_all` from the MATLAB run (`model/wamces_reference.mat`):

| | MATLAB | RAMSES |
|---|---|---|
| mean frequency, RMS difference over 50 s | | 4.9 mHz |
| nadir | 49.9551 Hz at 12.96 s | 49.9605 Hz at 13.70 s |
| steady state at 50 s | 49.9670 Hz | 49.9722 Hz |
| West minus East inter-area mode | 0.1400 Hz | 0.1398 Hz |
| that mode's peak-to-peak | 42.11 mHz | 41.72 mHz |

The inter-area mode agrees to 0.2 mHz and both match the roughly 0.13 Hz the paper quotes for the West to East mode, which is the headline result being replicated. The 5 mHz offset in the mean is against a 44 mHz total excursion and has at least three candidate causes that have not been separated: the reactive part of the step, which the reference does not have; the converters, absent from this run and present in the reference; and the single slack against the reference's five.

### The converters chattered under disturbance (fixed in RAMSES 3.83)

**Fixed in 3.83**: the full plant now runs the 51 s step in about 40 s. What follows is kept as the diagnosis record, and as the reason a full-plant disturbance must not be run on 3.82.

The complete plant initialises and sits still, but on a disturbance the 500 `GFOL` converters chatter on their `iq_1` limiter: over a million `REP UDIM GFOL 3` toggles, a `disc.trace` growing past 150 MB, and a 51 s run that does not finish. The machines-only case is unaffected and runs in 19 s.

It was a solver-robustness defect in the RAMSES engine, fixed in 3.83, not a modelling error, and it is worth being precise about that because the first two diagnoses in this folder's history were wrong.

`z(3)` is the switch on the `Idmax` block, which enforces the thermal limit by giving the q-axis priority and handing the d-axis the remaining headroom:

```
Idmax_stat = sqrt(max(Imax**2 - iq**2, 0))       then   Idmax = lag(Idmax_stat), bounded by [-Imax, Imax]
```

**The limit is correct and the bound must stay.** At `iq = 0` the full circle is available to `id` and `Idmax = Imax` by design: that is the unity-power-factor operating point, not a corner. The bound on `Idmax` is the hard guarantee that BDF2, which is not monotone, cannot push it past `Imax` numerically. Do not delete either; an earlier pass recommended exactly that and it was withdrawn.

**Be clear about which quantity is on the bound: it is `Idmax`, the headroom variable, not any current.** The worst-chattering unit carries `id` at 1e-13 and `iq` at 1e-8 against limits of 10, and the whole fleet's largest total current is 0.4 % of `Imax`. `Snom` plays no part: at `P0 = Q0 = 0` the output is zero on any base. What rests on the bound is the *amount of circle left for the d-axis*, which at `iq = 0` is all of it, and that headroom is then itself clamped to `[-Imax, Imax]`. It is a limiter on a limit; the current limiters one stage downstream are nowhere near active.

**The defect is that the switch on that headroom block has no deadband.** It enters on `Idmax > Imax` and exits on the sign of the lag's driving error, so when the headroom *rests* on its cap both tests are decided by solver noise on every step. The band is one Newton tolerance wide, not one ulp: with `$NEWTON_TOLER 1e-4` any `Idmax` within about 1e-4 of `Imax` is indistinguishable from being on it, which is `|iq|` below roughly `sqrt(2*Imax*tol)`, 0.014 pu at `Imax = 1` and 0.045 pu at `Imax = 10`. Measured: the worst converter has `id` at 1e-13 and `iq` at 1e-8, so its state is irrelevant to the physics and the trajectory is right; only the time is wrong.

Three things established by experiment, each of which rules out a tempting fix:

- **Raising `Imax` widens the band.** `Idmax_stat` scales with `Imax`, so the two move together and the tolerance band grows with them. Going from 1.0 to 10 made it worse.
- **Voltage control does not escape it.** `vqswitch = 1` moves `iq` to 1e-5 to 4e-2 and cuts the flipping from a million toggles to ten thousand, but 500 units of 10 MVA cannot move a 380 kV bus far enough to leave the band.
- **The model's own bypass is broken.** `Trlim < 0.001` sets `Imax = huge(0.d0)`, which overflows in `Imax**2`, so `Idmax_stat` is `Inf` and the run exits 255 after **0 time steps**.

A nonzero reactive dispatch does stop it (0.5 Mvar puts `Idmax_stat` 1.25e-4 below the bound, just outside tolerance, and takes the window from 337 steps in 28.4 s to 74 in 1.09 s), but it moves the operating point off the published one, so it is a diagnostic rather than a remedy. The fix belongs in the model, as a deadband on the switch using the `blocktol1` it already imports. Until then the disturbance case is machines-only, which is also what the paper's own validation in section 4.2 uses.

## The replication notebook

`PaperReplication.ipynb` is the end-to-end check, about half an hour to execute. What it depends on, none of it visible from the paper alone:

- **A run paused and resumed up to its STOP time is not finalised until `endSim()`.** Without it the trajectory stays a few hundred bytes and the extractor fails with `FortranEOFError`. The notebook's `finish()` calls it after every stepped run and after `getJac`; on a run that ended by itself it raises and is ignored.
- **`E_osc` (paper eq. 66) is over the 618 machine frequencies in Hz**, time step 10 ms. That reading reproduces the paper's 0.36 from the MATLAB run (0.358), which is why it was chosen; per unit, or over the PMUs, it does not.
- **`Kw` is not published** (zero in `data_gfm.csv`, not stated in the paper). A sweep put the paper's 80 % reduction of `E_osc` at about `Kw = 80` pu on the converter rating; the notebook shows 10, 40 and 80.
- **The forcing of Figure 13 is on grid-forming `Po`**, which RAMSES holds in pu on the converter's `Snom`, the base of the paper's `K_ampl`. The grid-following converters are 10 MVA and too small to reproduce the figure. The three sources and the envelope are chosen, not published.
- **The modal analysis is a sparse shift-invert on `getJac`**, local to the notebook (a reusable version for the stepss package has been proposed). It needs `$OMEGA_REF SYN` and runs the IBR configuration without the PMUs. `getJac` writes 170-280 MB of `py_*.dat` into the working directory, which is why the notebook `chdir`s into `runs/`.
- **The areas are the notebook's choice** (West ES, PT, FR; East the Balkans, RO, BG, GR, HU). The East-West mode shape checks it: Iberia against the Balkans and Greece, with France near the node.
- **The MATLAB comparison reads `reference/matlab_fig15_area_means.csv`**, which `tools/export_matlab_reference.py` reduces from `model/wamces_reference.mat` (git-ignored, 57 MB, written by `model/run_check.m` with stage C).

## Device model mapping

Decided: use registered library models wherever they exist, accept that converter dynamics differ from the paper, and drive the wide-area controller externally from `stepss-python-ui` rather than modelling it in the engine.

| WAMCES | n | RAMSES record | Notes |
|---|---|---|---|
| Synchronous machine | 618 | `SYNC_MACH` | parameter for parameter |
| AVR + PSS | 618 | `EXC ST1A_PSS2B` | exact, see below |
| Turbine | 618 | `TOR TGOV1` | `VMAX`/`VMIN`/`Dt` take defaults |
| Grid-forming converter | 300 | `INJEC GFOR` | swing dynamics map exactly, see below; voltage loop does not |
| Grid-following converter | 500 | `INJEC GFOL` | power loops map one-to-one; the PI PLL collapses to a first-order `tau` |
| PMU | 1573 | `INJEC PMU` | `Tf` from the PLL bandwidth, floored at 0.05 s; needs `$OMEGA_REF COI` for `dwref`/`thref` |

Every converter and PMU is dispatched at zero, so all three take `FP = FQ = 0` with zero `P` and `Q`, exactly as the machines do, and the load on their buses stays a residual impedance load.

**The grid-following converter maps better than its parameter count suggests.** Its two power loops are plain PIs on active and reactive power feeding current references, which are `GFOL`'s `Kpp`/`Kip` and `Kpv`/`Kiv` with `vqswitch = 0` selecting reactive power rather than voltage control. `Tr` is `Tlpf`. The one genuine reduction is the PLL: WAMCES uses a PI PLL, **hard-coded in the model as `60/wn` and `900/wn`** rather than read from `Tgfl.Kpllp`/`Tgfl.Kplli`, though the literals do match the table. That is second order with `wn = sqrt(900) = 30` rad/s and unity damping, and `GFOL` offers a single first-order `tau`, taken as `1/wn`. WAMCES has no inner current loop at all, so `GFOL`'s current control, limits and fault-ride-through thresholds take documented defaults.

`Imax = 1.0` pu on both converters is a documented default, not a WAMCES value: WAMCES models no current limit anywhere. It never binds at zero dispatch, but it would under a large enough disturbance.

**The PMU's `Tf` comes from its PLL, not from `Td`.** The WAMCES PMU is a PI phase-locked loop and nothing else (eq. 57 to 60), so its measurement dynamics are `wn = sqrt(Ki) = 30` rad/s at unity damping, an equivalent time constant of 0.033 s. `inj_PMU` clamps `Tf` below 0.05, so 0.033 s is not representable and the floor is emitted explicitly rather than left to the clamp. Taking `Td = 0.1` instead, as an earlier pass did, silently models the communication delay as measurement lag and double-counts it once a WAMC is attached.

**The grid-forming converter is a virtual synchronous machine, so `GFOR` fits.** Tracing the `synchronization loop` subsystem gives `dw/dt = Ki*(P0 - Pe - Kf*w)` and `ddelta/dt = wn*(w - w_sys)`, which is the swing equation. So `Ki = 1/(2H)`, giving **`H = 4 s`**, the same inertia as the synchronous machines, and `Kf` is the damping `D`. `Yf = -1.25i` inverts to `R = 0`, `L = 0.8 pu`. There is no droop term in the loop at all, so `Rdroop` is set not to respond, the same convention as Cyprus scenario C.

**The paper and the implementation disagree about `Ki`, by a factor of 64.** Equation 33 reads `Ki dw/dt = Pref - P - Kf w`, putting `Ki` on the left, which would make it `2H` and `H = 0.0625 s`. The Simulink block named `Ki` is a *gain feeding* the integrator, so the model actually simulates `dw/dt = Ki*(...)` and `H = 4 s`. Follow the source, exactly as with the `WT3` parameter contract: it is what runs, it matches the synchronous machines, and near-zero inertia would be a strange thing for a device whose stated job is emulating it.

**`Kw` is the wide-area damping control gain, not a droop.** It multiplies the difference between the delayed global frequency average and the local frequency (paper eq. 65), and the grid-forming converters are the actuators of that control. `wamces_script.m` sets `Tgfm.Kw(:) = 0`, which turns the wide-area control **off**: the published base case is open-loop, and that is what these data files reproduce. An externally driven WAMC injects its signal here.

**`Td` in `data_gfm` and `data_pmu` is a communication latency, not a measurement constant.** It parameterises the second-order Pade approximant of the wide-area link (eq. 61 to 63) and delays a PMU reading on its way to the central unit (eq. 64). It belongs to the control layer and must not be folded into a device's filter time constant. `GFOR`'s `Tpll` therefore takes the documented default rather than `Td`, since the WAMCES grid-forming converter is power-synchronised and has no PLL of its own.

What does *not* carry across is the voltage loop: WAMCES regulates terminal voltage with a PI (`Kvp`, `Kvi`) on a `Tr`-lagged measurement, and `inj_GFOR`'s ten data parameters expose no voltage-loop gains. Swing behaviour is faithful; voltage-regulation dynamics are not.

**The AVR needs no new model.** It looks like a gap because `ST1A` is a static exciter, but its amplifier block is `KA/(1+sTA)`, and that lag plays exactly the role of the WAMCES `TE`. The mapping is `Tr -> TR`, `TA -> TC`, `TB -> TB`, `KA -> KA`, `TE -> TA`, with `TC1 = TB1 = 0` to bypass the second lead-lag, `KF = 0` and `TF = 1` to disable rate feedback, and the limits opened out because WAMCES models none. The WAMCES PSS parameter set is a strict subset of PSS2B. `EXC ST1A` records in `stepss-GB-Network` use the same zero-bypass idiom.

The governor's data-file name is `TGOV1`, but the source file is `tor_TGOV1D.f90`: the dispatcher maps `case('tor_TGOV1')` to `tor_TGOV1D`. Do not go looking for `tor_TGOV1.f90`.

### The machines, and what the mapping rests on

Every one of the 618 machines is electrically identical (`Xd = 2`, `H = 4`, `Ra = 0`, `D = 0`, the lot) and differs only in its rating `Sr`, of which there are 473 distinct values. All 618 AVRs are one parameter set, all 618 PSSs another, all 618 turbines a third. So `wamces_dyn.dat` is one template repeated with a varying rating, and the positional join between the tables carries no information to get wrong.

The `XT` machine format maps one-to-one onto the WAMCES columns. Saturation is set to `m = n = 0` because WAMCES models none, and `IBRATIO = 1`.

Three choices that are not forced by the data:

- **`FP = FQ = 0` with explicit P and Q in MW**, never participation fractions. 613 of the 618 machine buses also carry load, 40.8 GW of it, so `FP = 1` would make each machine absorb its bus's *net* injection and understate generation by that amount.
- **`Pnom = SNOM`**, so the turbine base equals the machine base. In the MATLAB model mechanical power is per unit on `Sr`, so the droop `R = 0.33` only transfers unchanged if the two bases coincide.
- **Ratings are the up-rated ones, not `data_sm.csv`'s `Sr`.** `wamces_script.m` refuses to leave a machine dispatched above 80 % of nameplate and silently rewrites the rating to `sqrt(P^2+Q^2)/0.8`. It touches **39 of the 618 machines**, the worst at 293 % loading, whose rating goes from 100 to 366.4 MVA. This is not bookkeeping: `H` is per unit on the rating, so an up-rated machine's absolute inertia moves with it, as does its turbine base. `effective_rating()` reproduces the loop; its 39 indices and the worst-case loading match MATLAB's own printout to six decimals.
- **Every limit opened out** (`VMAX`, `VMIN`, `VIMIN/MAX`, `VAMIN/MAX`, `VRMIN/MAX`, `VS*`), because WAMCES models no limiter anywhere, and `Dt = 0`.

**The PSS is speed-only, and that is faithful rather than a simplification.** WAMCES wires it as `Add = speed + KS3 * power` then `Add1 = Add - power`, so with `KS3 = 1` the power path cancels identically. It has two washouts on speed, one on power, no transducer lag on speed and no ramp-tracking filter. RAMSES's PSS2B has the same topology, so setting `T6 = TW4 = T8 = T9 = T10 = T11 = 0` reproduces it exactly, including the cancellation. Do not "fix" the bypassed ramp-tracking filter into something active: that would make the power path stop cancelling and change the stabilizer.

### Running the full case needs RAMSES 3.82 or newer

At 3809 buses this case needs the full engine. Engines before 3.82 stop in the network reader with `You do not have license for more than 1000 buses`; see the v3.82 release notes for why that happened even with a correct `license.dat`. On an older engine the case cannot run at all. HELIOS has no bus limit, so the power flow half always runs.

It also needs `mxnzel` at 6e6, raised in the same release. The injectors dominate the integrated Jacobian, each costing roughly the square of its own state count, so the full plant needs 4.52e6 against the old 3e6 ceiling and stopped in `struc_net_jacob`. Counter-intuitively the 1573 PMUs are the cheapest part at 9 states each; the 500 `GFOL` at 52 states each cost ten times as much. Trimming the instrumentation is not a way round it. `mxnzel` is a compile-time `parameter`, so **a stale build will not pick up a change to it**: the value must be raised and then rebuilt from clean, or the same stop reappears with a figure that is already below the new ceiling. Sizing those arrays from the actual counts, instead of from a compile-time ceiling, is an open item for the engine.

On 3.82 the assembled plant runs 20 s in about 6.7 s over 1002 steps, and the flat run is flat across every device:

| Device | n | signals | worst relative drift |
|---|---|---|---|
| `SYNC_MACH` | 618 | 13 | 2.6e-11 |
| `GFOR` | 300 | 18 | 8.1e-15 |
| `GFOL` | 500 | 19 | 1.2e-14 |
| `PMU` | 1573 | 5 | 2.2e-16 |

Observing the injectors needs `INJEC *` in the observables file alongside `SYNC *`, which makes the trajectory about 270 MB for a 20 s run.


### The small bench

`tools/bench_machine.py` builds a two-bus case carrying *the same* `SYNC_MACH`, `EXC ST1A_PSS2B` and `TOR TGOV1` records, generated by the same functions, and runs it flat for 20 s. It exercises record syntax, parameter order and model initialisation under the 1000-bus free limit, so it stays useful on a machine that cannot run the full case at all. It currently passes with every state flat to 1e-14: rotor speed exactly 1.0, mechanical torque equal to electromagnetic torque, no drift. Run it after any change to the device mapping.

Note that RAMSES reports field voltage in the machine's own Park per-unit system, not the air-gap-voltage normalisation, so `FV` around 0.0014 pu against `FC` around 1.06 pu is correct and not a base error: it is `Rf * if` with `Rf` about 0.0012 pu.

## Reading the data from Python

Use the CSVs. The `data_*.mat` files hold MATLAB **tables**, which `scipy.io.loadmat` returns as an opaque struct under the key `'None'` with the column names gone; there is no variable name and no usable data in what comes back. `powerflow_sol.mat` is the exception, a plain double array that loads normally, and it is the one file the CSV export does not cover.

## Provenance and licence

Third-party data from the University of Palermo, published under CC BY through the paper and the Zenodo record. Per the parent repository's rule on non-SPS-L data, do not add an Apache 2.0 `LICENSE` to this folder; keep the PDF and the untouched archives as the provenance record. It is published as the public repository `SPS-L/stepss-WAMCES` and added to `stepss-test-systems` with a relative URL and its default branch, as the parent `CLAUDE.md` describes.
