# Image audit and maintenance

The ETL Dockerfile pins official multi-platform Python 3.13.16/Trixie and uv 0.12.0
image digests. Both Compose definitions pin the existing PostgreSQL 17.11/Alpine
digest; this records the tested image, not a database upgrade. The Python minor
version and existing locked package versions remain unchanged. The native client group
adds `psycopg-c` at the existing Psycopg 3.3.6 version. The runtime stays UID 65532.

The shared base stage uses the signed Debian snapshot `20261005T150126Z` and
Debian security snapshot `20261005T174018Z` in `docker/debian.sources`, replacing the
rolling repositories. Both builder and runtime use these dated package inputs.
`Check-Valid-Until: no` permits historical archive expiry; archive signatures and
TLS verification remain required. There is no rolling fallback. Advancing snapshots
requires a fresh build, tests, library inspection and vulnerability audit.

The shared base stage applies vendor security updates and installs the exact Debian
packages `libpcre2-8-0=10.46-1~deb13u3` and `libpq5=17.11-0+deb13u1` before both build
and runtime stages. Debian identifies this PCRE2 version as fixed for
[CVE-2026-103111](https://security-tracker.debian.org/tracker/CVE-2026-103111).
Base digests do not update automatically when a tag is rebuilt; updating and scanning
them is an explicit release operation. If the pinned package is unavailable, fail the
build and deliberately refresh the accepted version/digest rather than removing the pin.

Production selects the locked native dependency group and requires `PSYCOPG_IMPL=c`.
Exact `tool.uv.build-constraint-dependencies` and the hashed `build-tools` lock group
freeze setuptools, wheel, Cython, hatchling and their build dependency closure. The
pinned uv 0.12.0 supports version constraints rather than the newer hashed TOML form.
The builder first installs only locked build-tool wheels, builds without isolation,
then removes the tools, which are absent from the locked runtime dependency closure.
No shared uv cache can substitute a previously built native wheel. The locked Psycopg source archive contains generated C
and requires setuptools 83.0.0; Cython is pinned if regeneration is requested.
Updating tools requires explicit lock refresh and a cold native rebuild. These frozen
inputs do not claim byte-for-byte reproducible compiled wheels.
The compiler and libpq development headers exist only in the builder; runtime uses
system libpq and OpenSSL. Local default development keeps the binary wheel in the dev
group. The preceding binary-wheel image mapped bundled OpenSSL 1.1.1k with unverified
patch provenance; a version string does not prove a demonstrated exploit or absence of
backports. System linkage removes that maintenance gap. Check the resulting image's
library mappings, vendor versions and absence of bundled libraries independently.

The previous Python 3.13.14/Bookworm image's local Grype 0.120.0 scan found fixable
OpenSSL, PCRE2, interpreter and base-image pip matches. Python 3.13.16 contains the
published [interpreter security updates](https://www.python.org/downloads/release/python-31316/);
Trixie changes the base libraries, and its pip is 26.2.1. The independent backend
owner must apply and validate its own Dockerfile changes; ETL image changes do not
repair the running backend image.

Scan the exact resulting image against a current vulnerability database. Keep the raw
report, scanner/database version, source commit, platform and digest, including unfixed
and wont-fix matches. Counts may repeat one CVE for several packages. Scanner matches
do not establish remote exploitability, and zero fixable High/Critical matches does not
mean no vulnerabilities. Do not hide findings to make a release pass.

Remaining interpreter matches require explicit applicability review.
[CVE-2025-15367](https://raw.githubusercontent.com/CVEProject/cvelistV5/main/cves/2025/15xxx/CVE-2025-15367.json)
concerns POP3 command injection and includes Python 3.13.16 in the vendor's affected
range. This ETL implements no POP3/mail interface; retain the match and revisit it if
mail processing is added. Do not switch to a prerelease interpreter to clear a scan.
[CVE-2026-12345](https://raw.githubusercontent.com/CVEProject/cvelistV5/main/cves/2026/12xxx/CVE-2026-12345.json)
is a scanner/vendor range mismatch: the PSF record's affected ranges exclude Python
3.13.16. The exact Linux image also reports
`shutil.rmtree.avoids_symlink_attacks=True`. The advisory still describes platform and
file-flag limitations; the profiler and environment checker must retain private
temporary-directory ownership. Preserve the raw scanner finding and these facts;
neither match is suppressed in the audit.

The tested image's 55 High package matches represent 14 distinct CVEs. Debian's
minor/no-DSA decisions for some local utilities are maintenance policy, not fixes.
The libstdc++ allocation and binary-heap findings require native dependency review;
libstdc++ is loaded by the ETL's DuckDB import. zlib's vendor package status and
published upstream affected range also disagree. No safe available Debian 13 package
update was identified for these remaining findings. Retain them as unresolved launch
dispositions rather than claiming that Python source searches establish native safety.

Non-root execution alone does not prove privilege isolation. The image retains SUID
mount/umount/su files, and an ordinary disposable Docker run without explicit controls
reported `NoNewPrivs=0`. Both ETL Compose definitions now require a read-only rootfs,
dropped capabilities, no-new-privileges and private noexec/nosuid temporary storage.
State remains writable through its explicitly mounted private directories. Size and
monitor temporary storage for the workload; private tmpfs is not durable state. Verify
these controls, private volumes and no host socket, privileged mode or host namespace
access in the intended deployment. Do not blindly apply ETL capability settings to
PostgreSQL's root bootstrap process.

The PostgreSQL image also has retained scanner matches with no fix version recorded;
review Alpine/vendor status and the chosen deployment's exposure before launch. A
locked Python package audit excludes OS packages, interpreter and bundled libraries.

Verify image changes with `make check`, `make test`, non-root installed-package checks
and the complete disposable Compose proof in [demo-runtime.md](demo-runtime.md).
Keep backup/restore evidence separate from restart evidence. Never rebuild a shared
runtime while another owner holds its browser window, and never reset its data to
apply an image update.

## Reproducibility repair validation (2026-10-05)

The cold Linux arm64 build produced image
`sha256:6c4af0b04ad3d9b5c0d44fd60edfe379b54688cd09f62a3ba06ccdf24d9089e0`.
The image's `pyproject.toml` and `uv.lock` hashes match the reviewed build inputs.
No existing locked dependency version changed; the additional packages are build
requirements. A separate empty-cache negative check rejected altered setuptools
archive hashes, confirming the build-tools lock enforces artifact integrity.

Host checks passed all 244 tests; the image's Python 3.13.16/Psycopg C environment
passed locked checks, lint, formatting, environment checks and all 244 tests with
read-only source, non-root execution and no network. The exact production image
uses system libpq 17.11 and OpenSSL 3.5.7; compiler, headers, build-tool distributions
and the binary Psycopg wheel are absent. The native audit checked 110 ELF files and
found no targeted affected undefined references, subject to the limitations above.

All 13 disposable synthetic integration checks passed: publication/recovery,
role permissions, HTTP authentication/customer isolation, classifier reads,
refresh, persistence and cold recreation. Existing shared services and state were
not changed by this proof. The local Grype 0.120.0 database built
`2026-10-04T08:11:47Z` retains 183 matches: zero Critical, 55 High across the same
14 CVEs, 52 Medium, 10 Low and 66 Negligible; zero fixable High/Critical.
No custom suppression, image upload or external lookup was used. These checks
validate the frozen local candidate; they do not accept the remaining launch risks.
