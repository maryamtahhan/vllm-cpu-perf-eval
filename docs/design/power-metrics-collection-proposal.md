# Proposal: CPU Power & Energy Metrics Collection

Status: **Draft / Proposal** — not implemented
Scope: enable optional collection of CPU power & energy metrics for vLLM CPU inference
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

These are derived from two quantities we can obtain: **energy over the run window**
(new) and **token counts + timings** (already collected via `vllm-metrics.json` and
`benchmarks.json`).

---

## 2. Scope and non-goals

**In scope**

- Measure CPU + DRAM energy on **bare-metal x86** (Intel Xeon 6, AMD EPYC) using the
  kernel `powercap`/RAPL interface. No external hardware.
- Make collection a **first-class toggle** (on/off/auto) across Ansible, `cpueval`, and
  environment.
- Emit power samples + the four derived metrics into the existing results layout and
  Prometheus/Grafana.

**Out of scope (this proposal)**

- True *at-wall* energy at a hyperscaler (AWS gives no rack/PDU access to us).
- GPU/accelerator power.
- Full-system wall power via in-line meter / PDU / PowerSentry — described later as an
  optional "phase 3", not part of the base toggle.

---

## 3. Background: where the numbers come from

Both `turbostat` and `powertop` read the **same** kernel `powercap`/RAPL energy
counters; they are not independent instruments. The counters are exposed under
`/sys/class/powercap/*/energy_uj` (cumulative microjoules). Sampling `energy_uj`
deltas over an interval and dividing by that interval yields average power.

| Platform | Driver | Domains exposed |
| --- | --- | --- |
| Intel Xeon 6 | `intel_rapl_common` | package, core, uncore, dram, **psys** |
| AMD EPYC (Genoa/Turin) | `amd_rapl` | package, dram (package only on older kernels) |
| AWS Graviton (incl. `.metal`) | none | **none** (ARM, no powercap) |

`intel-rapl:psys` (Intel) measures platform power (socket + attached) and is the closest
on-die proxy to wall power; use it for the cost metric when present.

**Boundary caveat (must be recorded):** RAPL reports **CPU + DRAM at the silicon**. It
excludes PSU loss, PCH, fans, NIC, NVMe. This is the accepted figure for CPU-inference
efficiency, but it is *not* wall power. At-wall = RAPL x PUE (or Intel `psys`).

---

## 4. Key constraint: cloud vs bare metal (and AWS `.metal`)

**AWS EC2 virtualized (Graviton, Intel, AMD):** no `powercap` in the guest — energy
counters are hidden/zeroed by the platform. Measured watts are not available.

**AWS `.metal` instances:**

| Instance family | Powercap available? | Verdict |
| --- | --- | --- |
| Graviton `.metal` (m8g/m7g) | Never (ARM Neoverse has no powercap) | Measured **impossible** |
| x86 `.metal` (i4i / m7i / hpc6a) | *Maybe* — CPU is physical, but AWS does **not** document or guarantee the RAPL energy MSRs and they are typically zeroed/hidden | **Probe, do not assume** |

**Design consequence:** the toggle must not be "on for bare metal, off for AWS". It must
be **capability-probed with a manual override**. Concretely, we trust measured power only
when `energy_uj` files exist **and actually increment under load** — regardless of
whether the machine is on-prem or an AWS `.metal` box. If counters do not tick, we fall
back to modeled (off-cloud calibration) or off.

---

## 5. Design

### 5.1 Capability probe + mode resolution

A probe step sets `power_mode` before any collection:

```text
1. collect_power == false            -> power_mode = off
2. else probe:
     virt    = systemd-detect-virt            # "none" on real metal, else amazon/kvm
     domains = glob /sys/class/powercap/*/energy_uj
     live    = energy_uj increments during a ~200 ms busy spin
3. if domains and live              -> power_mode = measured
   elif model calibration available -> power_mode = modeled
   else                             -> power_mode = off   (+ warning)
```

`force_measured=true` pins the sampler but still refuses to emit `measured` numbers if
the counters are static (guards against silently reporting zeros on AWS metal).

| Target | Typical `systemd-detect-virt` | powercap live? | Resulting mode |
| --- | --- | --- | --- |
| On-prem Xeon 6 / EPYC | `none` | yes | `measured` |
| AWS `.metal` x86 (counters tick) | `none` | yes | `measured` |
| AWS `.metal` x86 (counters static) | `none` | no | `modeled`/`off` |
| AWS Graviton (any) | `amazon`/`kvm` | no | `modeled`/`off` |
| AWS EC2 virtualized x86 | `amazon`/`kvm` | no | `modeled`/`off` |

### 5.2 Sampler

Default sampler is a **native powercap reader at 1 Hz** writing
`power-samples.json` (timestamped like `vllm-metrics.json`), because it drops straight
into the existing Prometheus/Grafana stack. Per-socket/per-domain samples so multi-socket
and NUMA attribution is possible.

`power_collector_sampler: powercap | turbostat | off`

- `powercap` (default) — reads `energy_uj` deltas; no extra packages beyond base RHEL.
- `turbostat` — fallback via `kernel-tools`, logs `PkgWatt`/`RAMWatt`; epoch-aligned CSV.
- `powertop` — optional cross-check only (its "Power usage" line is a RAPL estimate, not
  an independent source); never the source of record.

### 5.3 New Ansible role: `power_collector`

Mirrors the lifecycle of `vllm_metrics_collector`:

```text
automation/test-execution/ansible/roles/power_collector/
  defaults/main.yml      # collect_power, power_collector_sampler, interval, domains, pue, price_per_kwh
  tasks/detect.yml       # capability probe -> power_mode
  tasks/start.yml        # start sampler in background on the DUT host (become: true)
  tasks/stop.yml         # stop sampler, fetch power-samples.json
  tasks/compute.yml      # derive the four metrics -> power-metrics.json
```

Run on the **host**, not inside the vLLM podman container, so `/sys/class/powercap` is
readable. Start/stop hooks slot into the same places as
`tasks/start-vllm-metrics-collection.yml` / `stop-...`.

### 5.4 Measurement window & attribution

- Integrate power only over each `benchmark_timings[].start_time/end_time`, excluding the
  existing 30 s warmup/cooldown, so idle/setup energy does not pollute per-run energy.
- Multi-socket: sum only the packages whose cores host the vLLM workers (derived from
  `cpuset_cpus` / NUMA map) for the "power under test", and also record the all-socket
  total, so a tp1 run is not charged an idle socket's power.

### 5.5 Deriving the four metrics

Post-process step joins `power-samples.json` (energy over window E, mean power P̄, window
Δt) with token totals (`prompt + generation`) from `vllm-metrics.json`/`benchmarks.json`:

```text
Mean Power (W)   = E / Δt
Energy/token     = E / tokens                       # J/token
Tokens/W         = 1 / (energy_per_token)           # token/J
$/1M tokens      = (energy_per_token * 1e6 / 3.6e6) * PUE * price_per_kwh
                   (+ optional amortized hardware: hw_cost_per_hr / tokens_per_hr)
```

Output: `power-metrics.json` per run, plus a `power` block appended to
`test-metadata.json` recording `power_mode`, vendor, domains used, PUE, price, and
`sut_boundary`, so every figure is auditable.

---

## 6. Toggling collection on/off

Three surfaces, consistent with existing `collect_*` flags:

| Surface | Example |
| --- | --- |
| Ansible extra-var | `-e collect_power=true` (or `false`, or default `auto`) |
| `cpueval` CLI / suite yaml | `--collect-power` / `collect_power:` field |
| Environment | `CPUEVAL_COLLECT_POWER` = auto / true / false |

`auto` (default) runs the probe in §5.1. Operators who want to force behavior in the
cloud can set `collect_power=false` (off) or `power_collector_sampler=turbostat` etc.

---

## 7. Modeled mode (for AWS, where measurement is impossible)

Keep AWS as the benchmark SUT but infer energy:

1. On on-prem Xeon 6 / EPYC (measured mode), sweep a per-CPU-model power model across the
   real workloads: `W = f(active_cores, utilization, frequency)`, recorded with the run.
2. In AWS, collect fine-grained in-guest utilization (node_exporter / `mpstat` +
   `cpufreq`) and evaluate the model to produce E, then the four metrics.
3. Stamp `power_mode: modeled` and store the calibration source + error bound in metadata.

CloudWatch `CPUUtilization` is a coarse fallback only. The AWS Customer Carbon Footprint
Tool is account-level and is **not** usable for per-run energy.

---

## 8. RHEL packaging (bare metal, x86)

| Tool | Role | RHEL repo |
| --- | --- | --- |
| `kernel-tools` (`turbostat`, `cpupower`) | sampler / frequency-idle control | **base** |
| `perf` (`power/*` events) | per-domain sampling | **base** |
| `sysstat` (`mpstat`) | utilization (modeled mode) | **base** |
| `tuned` | reproducible power/frequency profile | **base** |
| `powertop` | optional cross-check (documented in RHEL 10) | base (RHEL 10) / EPEL (RHEL 9) |
| `msr-tools` (`rdmsr`) | raw RAPL MSR debug only | EPEL |
| PowerSentry / pyredfish | phase 3 wall-power | no rpm — pip/venv |

Kernel modules `intel_rapl_common` / `amd_rapl` ship in RHEL 9/10 `kernel-core`; Xeon 6
and EPYC DRAM domain may need a current 9.x errata kernel — the probe verifies empirically
rather than assuming.

Install step: `dnf install -y kernel-tools perf sysstat tuned`, then gate on powercap
domains.

---

## 9. Reproducibility controls

Power is only meaningful if the machine behaves consistently between runs. Before
sampling, pin state via `tuned` (`virtual-host` / `latency-performance`), `cpupower`
(governor + idle-state disabling), and record the exact settings in metadata. Power runs
should note `power-profile` the same way latency runs note tuning knobs.

---

## 10. Accuracy caveats to record on every result

- At-silicon (CPU+DRAM) vs at-wall (x PUE) — state which is reported.
- Intel `psys` vs package+dram (different coverage).
- AMD package-only on older kernels (DRAM energy missing).
- Powercap ~60 Hz internal, our 1 Hz sampling; per-token energy over short windows is an
  average, not an instantaneous decode-power figure.
- Modeled mode is an estimate with a stated confidence interval, never labeled measured.

---

## 11. Deliverables / phases

- **Phase 1 (this proposal):** capability probe + `power_collector` role (measured,
  powercap sampler) + the four metrics + toggle across Ansible/CLI/env + Grafana panel.
- **Phase 2:** `turbostat` sampler fallback, multi-socket/NUMA attribution, reproducibility
  pinning, modeled mode + offline calibration harness.
- **Phase 3 (optional):** PowerSentry / BMC Redfish / PDU for true at-wall energy.

---

## 12. Configuration reference (proposed defaults)

```yaml
collect_power: auto            # auto | true | false
power_collector_sampler: powercap   # powercap | turbostat | off
power_collector_interval_s: 1
power_domains: [package, dram] # + psys on Intel when present
power_scope: socket-under-test # socket-under-test | all-sockets
power_pue: 1.0                 # 1.0 == at-silicon; set >1 for at-wall
power_price_per_kwh: null      # required to emit $/1M tokens
power_force_measured: false
```

---

## 13. Test plan

- Unit: window integration + metric math against synthetic power/token samples.
- Bare-metal smoke: probe reports `measured`, samples increment, `$`/tokens sane vs a
  known TDP ballpark.
- Cloud smoke: probe reports `modeled`/`off` (never fake `measured`); counters-static path
  exercised.
- Regression: with `collect_power=false`, result layout and runtime are unchanged.

---

## 14. Open questions

1. Default `power_pue` / `price_per_kwh` source (per-datacenter config vs per-run override)?
2. Emit modeled energy in AWS by default, or keep AWS strictly `off` until the calibration
   harness lands? (Inclination is to turn it off)
3. `psys` vs package+dram as the reported default on Intel.
4. Where to surface the four metrics: metadata only, metadata + Grafana, + MLflow tags.
