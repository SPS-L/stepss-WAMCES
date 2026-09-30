"""Reduce the upstream MATLAB run to the small reference the notebook compares against.

model/run_check.m ('ABC') runs the published Simulink model and writes
model/wamces_reference.mat, 57 MB and git-ignored like the rest of model/. That run
is the published base case: every converter in service and the wide-area gain Kw at
zero, which is the configuration of the paper's Figure 15. This script keeps what the
notebook needs from it:

- the mean frequency of the machines in each area (West, Centre, East), at the
  MATLAB sample time of 10 ms, for plotting against the RAMSES run;
- the oscillation energy E_osc of the paper's eq. (66), computed from all 618
  machine frequencies at full resolution, written into the file header.

    python3 tools/export_matlab_reference.py
"""
import csv
import pathlib

import numpy as np
import scipy.io as sio

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEST = {'ES', 'PT', 'FR'}
EAST = {'RO', 'BG', 'GR', 'RS', 'MK', 'AL', 'ME', 'BA', 'HU'}


def area(country):
    return 'West' if country in WEST else 'East' if country in EAST else 'Centre'


def main():
    csv_dir = ROOT / 'original-data' / 'csv'
    country = {r['ID']: r['Country'] for r in csv.DictReader(open(csv_dir / 'data_bus.csv'))}
    # the columns of f_all follow the rows of data_sm, one per machine
    areas = np.array([area(country[r['BusID']])
                      for r in csv.DictReader(open(csv_dir / 'data_sm.csv'))])

    ref = sio.loadmat(ROOT / 'model' / 'wamces_reference.mat')
    t = ref['f_all_t'].ravel()
    f = ref['f_all_y']                                   # Hz, one column per machine
    dt = float(np.diff(t).mean())
    e_osc = float(((f - f.mean(axis=1, keepdims=True)) ** 2).sum() * dt)

    out = ROOT / 'reference' / 'matlab_fig15_area_means.csv'
    out.parent.mkdir(exist_ok=True)
    cols = ['West', 'Centre', 'East']
    means = np.column_stack([f[:, areas == a].mean(axis=1) for a in cols])
    with open(out, 'w') as fh:
        fh.write('# Upstream WAMCES MATLAB/Simulink run, converters in service, Kw = 0 (paper Figure 15).\n')
        fh.write('# 1000 MW conductance step at bus 2178 at t = 0. Area-mean machine frequencies in Hz.\n')
        fh.write(f'# machines per area: ' + ', '.join(f'{a} {int((areas == a).sum())}' for a in cols) + '\n')
        fh.write(f'# E_osc over all {f.shape[1]} machines (paper eq. 66, f in Hz): {e_osc:.4f}\n')
        fh.write('t,' + ','.join(cols) + '\n')
        for row_t, row in zip(t, means):
            fh.write(f'{row_t:.2f},' + ','.join(f'{v:.6f}' for v in row) + '\n')
    print(f'wrote {out.relative_to(ROOT)}: {len(t)} samples, E_osc = {e_osc:.4f}')


if __name__ == '__main__':
    main()
