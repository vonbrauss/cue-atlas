# Third-party notices

Cue Atlas source is provided under the MIT license in LICENSE.

Dependencies are obtained separately by pip; their own licenses apply:

- PySide6 / Qt for Python: LGPLv3 / GPLv3 / commercial terms, depending on the component. https://doc.qt.io/qtforpython-6/licenses.html
- NumPy: BSD-3-Clause. https://numpy.org/doc/stable/license.html
- SciPy: BSD-3-Clause and bundled component notices. https://scipy.org/about/
- Mutagen: GPL-2.0-or-later. https://github.com/quodlibet/mutagen
- imageio-ffmpeg: BSD-2-Clause wrapper. FFmpeg binaries have separate LGPL/GPL terms according to build configuration. https://github.com/imageio/imageio-ffmpeg
- FFmpeg: https://ffmpeg.org/legal.html and https://ffmpeg.org/download.html
- openpyxl: MIT. https://openpyxl.readthedocs.io/
- PyInstaller (build tool): GPL with a bundling exception. https://pyinstaller.org/en/stable/license.html

A packaged application includes third-party components. Preserve their applicable license notices and comply with their source and redistribution requirements if distributing a built bundle. Mutagen's GPL terms are especially relevant to redistribution of a combined application. This source archive does not include downloaded dependency binaries. The MIT license covers the original Cue Atlas code only and does not override dependency licenses.


## Optional BandIt music separation

The main app includes adapter code and attribution assets, but does not bundle the AI model or its runtime. Users may explicitly install them from Project settings.

- BandIt/BandIt v2: Karn N. Watcharasupat, Chih-Wei Wu, Iroro Orife, Apache License 2.0. [Official project](https://github.com/kwatcharasupat/bandit-v2). See `cueatlas/ai_assets/LICENSE-Apache-2.0.txt`.
- Inference adapter: ZFTurbo Music-Source-Separation-Training, commit `6fdad13686bb7e84d029ec66f9dbe76e65c93ebf`, MIT License. See `cueatlas/ai_assets/LICENSE-MIT.txt` and `NOTICE.txt`.
- Multilingual BandIt weights: [Zenodo record 12701995](https://zenodo.org/records/12701995), Creative Commons Attribution-ShareAlike 4.0. The downloaded checkpoint is verified against SHA-256 `abcfccf65446752a057f4a302c941479a54b7560ebf8d7bca039d2ea98e64cfc`.
- Optional runtime uses python-build-standalone and the packages pinned in `cueatlas/ai_assets/requirements.txt`. Their license notices remain in the installed runtime and package metadata.
