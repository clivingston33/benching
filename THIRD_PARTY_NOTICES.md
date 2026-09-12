# Third-party notices

First-party Benching code, documentation, tests, and first-party examples are
covered by the root [`LICENSE`](LICENSE) (MIT) unless a file or directory
says otherwise. This document lists everything else shipped in this
repository that requires attribution, has a separate license, or is someone
else's trademark. Transitive pip/npm dependencies are *not* listed here;
only files copied or vendored into the repository, and directly integrated
external tools, are in scope.

## Vendored UI code

### `dashboard/dither-kit/` — first-party, MIT

React chart/UI toolkit (ordered-dither charts plus generative UI
components), developed in this repository's own history by the repository
author (see `git log -- dashboard/dither-kit/`). The per-file comments
describe the components as ports of `.vue` single-file components from the
author's own earlier Vue kit; those `.vue` originals were never committed
to this repository and no third-party source, upstream URL, or foreign
copyright header was found anywhere in the directory (searched
September 2026). The directory's `package.json` declares `MIT`, consistent
with the root license. No third-party attribution is required. If a future
contribution introduces externally sourced code here, it must be listed in
this document with its upstream and license.

## Brand assets (trademarks, not owned by this project)

### `dashboard/public/kourier.svg`, `electron.svg`, `deepseek.svg`

Provider logo files used only for provider identification in
`dashboard/lib/provider-presentation.ts`. These are the trademarks of
their respective owners (Kourier, ElectronHub, DeepSeek). They are not
covered by the root MIT license grant — a copyright license is not a
trademark license. They are retained solely as nominative identification
glyphs and will be replaced with generic glyphs on request of a rights
holder. `dashboard/public/fireworks.svg` is a generic first-party glyph,
not a brand mark.

> All product names, logos, and brands are property of their respective
> owners. Use of these names, logos, and brands does not imply endorsement.

## External execution tools (not shipped, separate licenses)

Benching shells out to the following tools at run time. They are **not**
part of this repository, are not covered by its license, and are governed
by their own upstream licenses:

| Tool | Role | Upstream |
|---|---|---|
| Docker | task container execution | https://www.docker.com/ |
| Harbor | terminal-task benchmark runner (`harbor run`, Terminal-Bench-compatible task format) | your Harbor installation's own distribution and license |
| OMP (`oh-my-pi`) | instrumented agent binary, pinned via `Dockerfile.omp-cache` (`OMP_VERSION`) | https://github.com/can1357/oh-my-pi |

No code from these projects is vendored here. `Dockerfile.omp-cache`
downloads a pinned upstream release binary at image-build time; review the
upstream release before rebuilding.

## Direct dependency licenses (verified September 2026)

All direct runtime dependencies are permissive (MIT / Apache-2.0 /
BSD / ISC). No GPL, AGPL, SSPL, BUSL, PolyForm, Commons Clause, or other
source-available/non-OSS license was found among direct dependencies.

Python (`pyproject.toml`):

| Package | License |
|---|---|
| PyYAML | MIT |
| tokenizers | Apache-2.0 |
| huggingface_hub | Apache-2.0 |
| typer | MIT |
| rich | MIT |
| prompt_toolkit | BSD-3-Clause |
| jsonschema | MIT |

Node (`dashboard/package.json`):

| Package | License |
|---|---|
| ajv | MIT |
| clsx | MIT |
| d3-scale, d3-shape | ISC |
| html-to-image | MIT |
| motion | MIT |
| next | MIT |
| react, react-dom | MIT |
| tailwind-merge, tailwindcss | MIT |
| typescript | Apache-2.0 |
| tsx | MIT |

Licenses verified from installed package metadata (`importlib.metadata` /
`node_modules/*/package.json`), not from memory.
