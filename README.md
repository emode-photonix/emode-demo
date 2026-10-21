# Try EMode now

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/emode-photonix/emode-demo/blob/main/EMode_demo.ipynb)

A notebook that runs [EMode](https://emodephotonix.com), the photonic waveguide mode solver, in your browser. Open it in Google Colab, run the cells, and within about a minute you see the modes of a silicon waveguide, their fields as numpy arrays, and a width sweep. You need no EMode account and nothing on your computer.

> This repository is private until it is reviewed. Until then the badge above opens the notebook only for someone signed in to Colab with a GitHub account that can see `emode-photonix/emode-demo`.

## How it works

The first cell, "Set up EMode", does everything a visitor would otherwise do by hand:

1. Asks `https://emodephotonix.com/wp-json/custom/v1/demo-credentials/` for the demo account, the EMode release to install, that release's SHA-256 and the demo license manager. If the demo is paused, it prints the reason and stops.
2. Installs the `emodeconnection` client library from PyPI, at the version this notebook is written for.
3. Downloads the lighter Linux build of EMode (`Linux-rslab`), checks its SHA-256 against the published one, and installs it. Nothing is installed when the checksum does not match.
4. Stores the demo login with `emode login --write`, points EMode at the demo license manager (`EMODE_LICENSE_URL`), and opens a session.

The demo password changes once a day. If that happens while the cell runs, the cell fetches the new one and tries again once. Running the cell a second time skips what is already done. The password is never printed.

The notebook runs in any Jupyter on Linux, and Colab is the first target. On other systems the setup cell stops and points to the free EMode2D license instead.

## The demo's limits

- **EMode2D only.** The mode solver, without EME or 3D.
- **60 minutes per session.** After that, every call answers with how to get a free EMode2D license. Run the setup cell again for a new session.
- **Shared and capped.** Every visitor uses the same demo account, and the number of sessions at one time is limited. When it is full, the setup cell says the demo is busy.

Running the setup cell installs EMode and accepts the [EMode EULA](https://emodephotonix.com/legal/eula.pdf).

## Nightly check

`.github/workflows/nightly.yml` runs the notebook headless every night at 11:00 UTC (and on demand from the Actions tab) on Ubuntu 22.04 and the latest Ubuntu, with `jupyter nbconvert --execute`, then `ci/check_executed.py` fails the run if any cell raised an error or a figure is missing. It uses the live credential endpoint, one request per job, and needs no secrets.

While the demo is paused, the endpoint answers `enabled: false`, the setup cell stops with `DemoPaused`, and the run passes with a notice that shows the pause message. So the nightly run is green but proves nothing beyond the notebook's paused path until the demo opens.

To run it against the live demo once it is open (or during a rehearsal with the endpoint enabled), start the workflow from the Actions tab ("Nightly notebook run", "Run workflow"), or locally on Linux:

```bash
python -m pip install nbconvert nbclient ipykernel matplotlib numpy
jupyter nbconvert --to notebook --execute --allow-errors --output executed.ipynb EMode_demo.ipynb
python ci/check_executed.py executed.ipynb
```

Each run makes one request to the credential endpoint, which allows 10 per address per hour.

`.github/workflows/tests.yml` tests the setup cell against mocks on every push and pull request (`tests/`), with no network and no EMode.

## Contact

Questions, or something not working? Write to [hello@emodephotonix.com](mailto:hello@emodephotonix.com).

## License

TODO(#1): choose a license for this repository (BSD-3-Clause or MIT). EMode itself is licensed under the [EMode EULA](https://emodephotonix.com/legal/eula.pdf).
