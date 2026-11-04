# Third-party components

SCIO CODE is an independent client, not an official Scio or OpenCode release.

- Terminal UI: [OpenCode](https://github.com/anomalyco/opencode), public MIT-licensed source v1.19.3 plus `branding/scio-code.patch`. Copyright (c) 2025 opencode. Full license: `licenses/OPENCODE-LICENSE.txt` in the distribution and beside the UI executable.
- Python 3.14.10: official [Windows embeddable package](https://www.python.org/downloads/release/python-31410/). PSF license and third-party notices: `runtime/LICENSE.txt`.
- cloudflared 2026.10.7: [Cloudflare tunnel client](https://github.com/cloudflare/cloudflared), Apache License 2.0. Full license: `licenses/CLOUDFLARED-LICENSE.txt`. Source and dependency notices are available in the linked upstream tag.
- Python dependencies are pinned with wheel hashes in `requirements-dist.lock`. Their original metadata and license files are retained under `runtime/Lib/site-packages/*.dist-info`.

No leaked or proprietary Claude Code harness source is included. Scio credentials and user data are not part of the distribution.
