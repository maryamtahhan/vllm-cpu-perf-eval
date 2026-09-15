# Proposal: CPU Power & Energy Metrics Collection (PCP + JouleIT)

Status: **Draft / Proposal** — not implemented

Related: `docs/metrics-collection.md`, `automation/test-execution/ansible/roles/vllm_metrics_collector`

---

## 1. Motivation

Performance results today capture throughput and latency but not energy. For CPU
inference the interesting efficiency questions are:

| Metric | Unit | Definition |
| --- | --- | --- |
| Mean Power Consumption | W | Average socket power over the measurement window |
| Energy per token | J/token | Energy consumed divided by tokens processed |
| Tokens per Watt | token/J | Sustained throughput per unit power |
| Million-token cost | $/1M tokens | Marginal energy cost of one million tokens |

These are derived from two quantities: **energy over the run window** (to be collected)
and **token counts + timings** (already collected via `vllm-metrics.json` and
`benchmarks.json`).

---

## 2. Why PCP and JouleIT (vs. a hand-rolled sampler)

Both are built on the same powerapi-ng / RAPL substrate, so their numbers agree, and both
cover the measurement paths we need. Choosing them removes a custom collector from our
maintenance surface and leans on Red Hat-supported tooling.

**PCP (Performance Co-Pilot)** — Red Hat's own framework, shipped in RHEL. Relevant
pieces already present in the source tree (v7.2.2 in this checkout):

- `pmdadenki` — electricity PMDA. Metrics:
  - `denki.rapl.sysfs` — cumulative Joules per RAPL domain (package / core / uncore /
    dram), read from `/sys/class/powercap`, **per-socket instances** (multi-NUMA aware).
  - `denki.rapl.msr` — cumulative Joules via MSR, domains incl. **`psys`** (platform power).
  - Rate-converted, these become **Watts** directly (`pmrep`, `pmval`).
- `pmdaperfevent` — optional Intel RAPL events (`RAPL:PACKAGE_ENERGY`,
  `RAPL:DRAM_ENERGY`, `THERMAL_SPEC`, `MINIMUM/MAXIMUM_POWER`).
- `pmlogger` — records a time-series archive per run; `pmrep` / `pmlogextract` render it;
  `pmproxy` + Redis exposes it to a **Grafana datasource** (complements our existing
  Prometheus/Grafana stack). `pmdalinux` supplies CPU utilization + frequency (modeled-mode
  inputs); `tuned` integration for reproducible state.

**JouleIT (powerapi-ng)** — `sudo jouleit.sh <cmd>` wraps a command, samples RAPL for its
whole lifetime, and reports energy for CPU + DRAM (+ iGPU). Flags we use: `-g` (aggregate
sockets), `-s s0,s1` (select sockets), `-b` (KEY:VALUE energy out), `-n/-j` (repeat +
CSV). It is **process/run-scoped** — the natural tool for a bounded job and for the
off-cloud calibration sweep.

Summary of roles:

| Tool | Role |
| --- | --- |
| PCP `pmdadenki` + `pmlogger` | Continuous, time-aligned power source of record (online/server runs); Grafana viz |
| PCP `pmdalinux` / `tuned` | Utilization + frequency inputs; reproducible state |
| PCP `process` PMDA | Per-process CPU time (attribution context, §5.7) — not a power source |
| JouleIT | Per-run energy for bounded workloads + calibration |
| Redfish / BMC (exporter or direct poll) | Whole-chassis PSU watts (system scope, at-wall-ish) |

**On Redfish:** PCP has **no native Redfish PMDA in this tree** (v7.2.2) — `denki` is the
only built-in power source. BMC power is brought in either by polling the BMC Redfish
`Chassis/Power` (or `PowerSubsystem/PowerSupplies`) resource directly (`python-redfish` /
`curl`) or via a Redfish→Prometheus exporter scraped through PCP's `pmdaopenmetrics`. It
reports **whole-system input watts** — vendor-agnostic (EPYC, Xeon, even bare-metal ARM) and
the closest thing to at-wall power without a meter — but it is **chassis-granularity** (no
per-socket / per-process) and updates slowly (~1 s+). Not available in AWS (no BMC exposed).
Use it as a system-scope / cost signal that complements `denki`'s CPU+DRAM-silicon numbers.

---

## 3. Scope and non-goals

**In scope**

- Measure CPU + DRAM energy on **bare-metal x86** (Intel Xeon 6, AMD EPYC) via PCP
  (`pmdadenki`, optionally `pmdaperfevent`) and JouleIT. No external hardware.
- Make collection a **first-class toggle** (on/off/auto) across Ansible, `cpueval`, env,
  and the PCP PMDA install state.
- Emit power time-series + the four derived metrics into the existing results layout and
  Grafana.

**Out of scope (this proposal)**

- True at-wall energy at a hyperscaler (no rack/PDU access).
- GPU/accelerator power.
- In-line meter / PDU / PowerSentry full-system energy (optional "phase 3").

---

## 4. Key constraint: cloud vs bare metal (and AWS `.metal`)

Energy counters come from RAPL/`powercap`. Availability:

| Platform | Driver | Coverage |
| --- | --- | --- |
| Intel Xeon 6 | `intel_rapl_common` (sysfs) + MSR | package, core, uncore, dram, psys |
| AMD EPYC (Genoa/Turin) | `amd_rapl` (sysfs) | package, dram (package-only on older kernels) |
| AWS Graviton (incl. `.metal`) | none | none (ARM, no powercap) |
| AWS EC2 virtualized (Intel/AMD) | masked | none in-guest |
| AWS x86 `.metal` (i4i / m7i / hpc6a) | physical CPU, but AWS does not document/guarantee the energy MSRs | typically hidden/zeroed — **probe, do not assume** |

PCP makes the probe trivial and uniform: with the PMDA installed, `pminfo denki.rapl.sysfs`
either returns incrementing instances or it does not. JouleIT likewise simply aborts when
no RAPL domain is present. So we trust measured power **only when counters exist and tick**,
regardless of on-prem vs AWS `.metal`.

| Target | `systemd-detect-virt` | `pminfo denki.rapl.sysfs` ticks? | Resulting mode |
| --- | --- | --- | --- |
| On-prem Xeon 6 / EPYC | `none` | yes | `measured` |
| AWS `.metal` x86 (counters tick) | `none` | yes | `measured` |
| AWS `.metal` x86 (static) | `none` | no | `modeled` / `off` |
| AWS Graviton (any) | `amazon` / `kvm` | no | `modeled` / `off` |
| AWS EC2 virtualized x86 | `amazon` / `kvm` | no | `modeled` / `off` |

---

## 5. Design

### 5.1 Capability probe + mode resolution

Run before collection; sets `power_mode`:

```text
1. collect_power == false                    -> off
2. ensure pmdadenki installed (best-effort)  # the actual on/off at the collector
3. probe:
     virt    = systemd-detect-virt          # "none" on real metal
     domains = pminfo --check denki (instances of denki.rapl.sysfs)
     live    = denki.rapl.sysfs increments during a ~200 ms busy spin
4. if domains and live                      -> measured
   elif model calibration available          -> modeled
   else                                      -> off   (+ warning)
```

`power_force_measured=true` keeps the pipeline on but still refuses to emit `measured`
numbers when counters are static (guards against reporting zeros on AWS metal).

### 5.2 Continuous collection with PCP (source of record)

- Start a **`pmlogger` archive scoped to the run** capturing `denki.rapl.sysfs`,
  `denki.rapl.msr`, and `pmdalinux` util/frequency, at a 1 s interval (tighter than the
  default 2 s pmcd fetch) for finer windows.
- After the run, `pmlogextract`/`pmrep` over the PCP archive produce
  `power-samples.json` (timestamped like `vllm-metrics.json`), one series per domain per
  socket.
- Power = rate-converted energy (PCP reports cumulative J; deltas / Δt = W).
- `pmproxy` feeds the same archive to our Grafana for live/retro visualization; no parallel
  Prometheus power exporter needed.

### 5.3 Per-run energy with JouleIT (bounded workloads + calibration)

- For workloads whose **process lifetime equals the measurement window** (e.g. the
  offline-batch suite), wrap with JouleIT to get attributable energy directly:
  `sudo jouleit.sh -b -s <sockets> <cmd>` → energy (J) for CPU/DRAM over that run.
- For the **server + external-client** (concurrent-load) case, the SUT is a long-running
  server driven by an external benchmark, so JouleIT can't bracket just the load; there we
  use the PCP time-window method (§5.4) instead. Optionally run the server under JouleIT
  for a whole session and subtract an idle baseline.
- Calibration (Phase 2, §7) runs the offline-batch workloads under JouleIT on bare metal to
  fit `W = f(active_cores, utilization, frequency)`; PCP supplies utilization/frequency.

### 5.4 Measurement window & attribution

- Integrate energy only over each `benchmark_timings[].start_time/end_time`, excluding the
  existing 30 s warmup/cooldown, so idle/setup energy does not pollute per-run energy.
- Multi-socket / NUMA: PCP's per-socket instances plus our `cpuset_cpus` map let us sum
  only the packages whose cores host the vLLM workers (power under test), while also
  recording the all-socket total, so a tp1 run is not charged an idle socket's energy.

### 5.5 Deriving the four metrics

Join energy over the window (E), mean power (P̄), window Δt, and token totals
(`prompt + generation` from `vllm-metrics.json` / `benchmarks.json`):

```text
Mean Power (W)   = E / Δt
Energy/token     = E / tokens                       # J/token
Tokens/W         = 1 / (energy_per_token)           # token/J
$/1M tokens      = (energy_per_token * 1e6 / 3.6e6) * PUE * price_per_kwh
                   (+ optional amortized hardware: hw_cost_per_hr / tokens_per_hr)
```

Output: `power-metrics.json` per run, plus a `power` block in `test-metadata.json`
recording `power_mode` (`measured` / `modeled` / `off`), backend used
(`pcp-denki` / `pcp-perfevent` / `jouleit` / `redfish`), the sockets/cores attributed, vendor,
domains, PUE, price, and `sut_boundary` — so every figure is auditable.

### 5.6 New Ansible role: `power_collector`

Mirrors `vllm_metrics_collector` lifecycle:

```text
automation/test-execution/ansible/roles/power_collector/
  defaults/main.yml   # collect_power, sampler, sockets, pue, price_per_kwh
  tasks/detect.yml    # probe -> power_mode
  tasks/start.yml     # pmdadenki install (if needed) + pmlogger archive (+ JouleIT wrapper)
  tasks/stop.yml      # stop archive/wrapper; pmlogextract -> power-samples.json
  tasks/compute.yml   # derive four metrics -> power-metrics.json + metadata block
```

Runs on the **host**, not inside the vLLM container (RAPL/powercap must be readable).
Hooks slot in beside `tasks/start-vllm-metrics-collection.yml` / `stop-...`.

### 5.7 Attribution & topology (per-core power is not available)

RAPL/`powercap` granularity on Xeon 6 and EPYC is **per socket** (one package zone per
socket) plus in-socket aggregate domains (`core` = *all* cores summed, `uncore`, `dram`).
There is **no per-logical-core and no per-PID / per-cgroup energy**. JouleIT's `-s` selects
sockets, not cores, and PCP `denki.rapl.sysfs` instances are per socket/domain. So we cannot
carve out exactly "the cores vLLM is pinned to" unless that set equals a whole socket.

Consequence for running the load generator (guidellm) and vLLM on **one host**:

| Topology | Separable? | How |
| --- | --- | --- |
| Loadgen on a **separate host** (current `load_generator` group) | Yes | DUT package energy = power under test (clean) |
| Same host, **different sockets** (vLLM numa0 / guidellm numa1), vLLM socket otherwise idle | Yes | Report `socket-under-test` package energy |
| Same host, **same socket** shared | No | Not measurable — only a CPU-time-share estimate |
| Single-socket host (e.g. Graviton) | N/A | No RAPL in-guest anyway |

**Limitation (documented, not enforced):** measured energy is per-socket only, so it cannot
be attributed to a single process. "vLLM power" is only defensible when the load generator
does **not** share the measured socket — i.e. a separate loadgen host, or a disjoint-socket
split with the vLLM socket otherwise idle (recorded on the result as `power_scope`). When the
load generator shares the measured socket, the only honest outputs are the per-socket or
all-socket totals; a per-process split would just apportion by CPU-time share (a rough
estimate, not a measurement) and is out of scope here. Redfish is no help — it is
whole-chassis. This is recorded on every result rather than blocked.

Net: for a clean measured figure the load generator should be on a **separate DUT**, or on a
disjoint socket with the vLLM socket otherwise idle. Pinning cores and using `resctrl` /
`isolcpus` keeps housekeeping off the measured socket. These are preconditions we surface to
the user, not gates the tool enforces.

---

## 6. Toggling collection on/off

| Surface | Example |
| --- | --- |
| Ansible extra-var | `-e collect_power=true` (values: auto / true / false) |
| `cpueval` CLI / suite yaml | `--collect-power` / a `collect_power:` field |
| Environment | `CPUEVAL_COLLECT_POWER` = auto / true / false |
| Collector-level | `pmdadenki Install` / `Remove` (`$PCP_PMDAS_DIR/denki`) |

`auto` (default) runs the probe in §5.1. In the cloud, operators can force
`collect_power=false` (off) or keep `auto` and land in `modeled`.

---

## 7. Modeled mode (AWS, where measurement is impossible)

Keep AWS as the benchmark SUT but infer energy, using PCP on both sides so the interface is
identical:

1. On on-prem Xeon 6 / EPYC (`measured`), sweep per-CPU-model `W = f(active_cores,
   utilization, frequency)` across the real workloads, energy from JouleIT, util/freq from
   `pmdalinux`, recorded with the run.
2. In AWS, evaluate the model from PCP-collected util/frequency to produce E, then the four
   metrics, stamped `power_mode: modeled`.
3. Store calibration source + error bound in metadata.

CloudWatch `CPUUtilization` is a coarse fallback only; the AWS Customer Carbon Footprint
Tool is account-level and not usable per-run.

---

## 8. Packaging / availability

| Component | Where it comes from | Notes |
| --- | --- | --- |
| PCP (`pmcd`, `pmlogger`, `pmrep`, `pmproxy`) | RHEL **base** (`pcp`; optionally `pcp-zeroconf`) | Red Hat supported |
| `pmdadenki` (RAPL energy) | part of PCP ≥ ~6.0 | **verify RHEL-bundled PCP ships it**; RHEL 9's may predate it — may need a newer `pcp` build (this checkout is 7.2.2) |
| `pmdaperfevent` RAPL (Intel) | part of PCP | Intel only; config `<RAPL>` events |
| JouleIT (powerapi-ng) | git clone; conda/pip deps (`denki`/HWInfo, `hwloc`) | not an RPM |
| Redfish/BMC power | no RPM — `python-redfish` / `curl`, or a Redfish exporter scraped by `pmdaopenmetrics` | whole-chassis watts; bare metal only |

The `cpueval` installer already bootstraps a venv + dnf; JouleIT's conda/pip deps fit that
pattern.

---

## 9. Verification items (to close before Phase 1 merge)

1. **AMD EPYC enumeration** — confirm `pmdadenki` sysfs picks up `amd_rapl` package + dram
   instances (its MSR path and `pmdaperfevent` RAPL are Intel-only). If it only matches
   `intel-rapl*`, EPYC needs a newer PCP or a small PMDA tweak.
2. **RHEL PCP version** — confirm the distro `pcp` includes `pmdadenki`; otherwise pin a
   build.
3. **Sampling resolution** — set pmlogger interval to 1 s and check counter wrap handling
   for long runs.
4. `psys` availability on the target Xeon 6 (MSR path).
5. **Redfish** — confirm the BMC exposes a `Power` / `PowerSubsystem/PowerSupplies` resource
   with a usable update rate, and whether to bridge via `pmdaopenmetrics` vs direct poll.

---

## 10. Accuracy caveats to record on every result

- At-silicon (CPU+DRAM) vs at-wall (x PUE) — state which is reported; Intel `psys` (MSR)
  is the closest on-die wall proxy.
- AMD package-only on older kernels (DRAM energy missing).
- JouleIT reports energy over the **whole selected socket(s)** for the wrapped command's
  lifetime, not a single PID's threads — attribute accordingly.
- 1 s sampling averages power; per-token energy over short windows is a window average.
- **No per-core / per-PID energy** — only per-socket (+ aggregate core/uncore/dram). If the
  load gen shares vLLM's socket, report per-socket/all-socket totals only (§5.7).
- Modeled mode is an estimate with a stated confidence interval, never labeled measured.

---

## 11. Deliverables / phases

- **Phase 1 (this proposal):** capability probe + `power_collector` role using PCP
  `pmdadenki` + `pmlogger` (measured), JouleIT wrapper for offline-batch, the four metrics,
  toggle across Ansible/CLI/env, and a Grafana panel via `pmproxy`; attribution limitation
  documented on results (§5.7).
- **Phase 2:** modeled mode + offline calibration harness (JouleIT energy vs PCP util/freq);
  multi-socket/NUMA attribution; reproducibility pinning (`tuned`, governor).
- **Phase 3 (optional):** Redfish/BMC system-scope power (via `pmdaopenmetrics` or direct
  poll) and/or PowerSentry / PDU for true at-wall energy.

---

## 12. Configuration reference (proposed defaults)

```yaml
collect_power: auto                 # auto | true | false
power_backend: pcp                  # pcp | jouleit | pcp+jouleit
power_pcp_metrics: [denki.rapl.sysfs, denki.rapl.msr]
power_pcp_interval_s: 1
power_sockets: auto                 # auto (socket-under-test) | all | comma list for jouleit -s
power_scope: socket-under-test      # socket-under-test | all-sockets
power_pue: 1.0                      # 1.0 == at-silicon; >1 for at-wall
power_price_per_kwh: null           # required to emit $/1M tokens
power_force_measured: false
power_redfish: false                # also collect BMC system power via Redfish
power_redfish_endpoint: null        # e.g. https://bmc/ ; via pmdaopenmetrics or direct poll
```

---

## 13. Test plan

- Unit: window integration + metric math against synthetic energy/token samples.
- Bare-metal smoke: `pminfo -fT denki` shows incrementing domains; `power_mode=measured`;
  JouleIT energy on an offline-batch run is sane vs a known TDP ballpark.
- EPYC probe: verify AMD package (and dram) instances per §9.1.
- Cloud smoke: probe reports `modeled`/`off` (never fake `measured`); static-counter path.
- Attribution: separate-host run yields `measured`; same-host same-socket co-location is
  recorded with the documented per-socket/all-socket limitation (§5.7).
- Regression: with `collect_power=false`, result layout and runtime unchanged.

---

## 14. Open questions

1. Default `power_backend` for online runs — PCP-only, or PCP continuous + JouleIT-on-batch?
2. Default `power_pue` / `price_per_kwh` source (per-datacenter config vs per-run override)?
3. Emit modeled energy in AWS by default, or keep AWS `off` until the calibration harness lands?
4. `denki.rapl.msr` (psys) vs `denki.rapl.sysfs` (package+dram) as the reported default.
5. Ship our own pinned PCP build (to guarantee `pmdadenki` + EPYC support) or require an
   OS `pcp` version?
6. Same-host same-socket co-location — **resolved: documented as a limitation (§5.7), not
   enforced**; results record the per-socket/all-socket scope rather than being blocked.
