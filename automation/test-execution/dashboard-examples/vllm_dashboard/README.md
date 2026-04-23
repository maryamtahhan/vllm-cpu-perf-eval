# vLLM CPU Performance Dashboard (Multipage App)

Comprehensive performance analysis dashboard for vLLM CPU benchmarks.

## Features

**Single URL Access**: All dashboards accessible from `http://localhost:8501`

**Five Views**:
- 🏠 **Home** - Overview, quick start, system status
- 📊 **Client Metrics** - GuideLLM performance analysis (LLM models)
- 🖥️ **Server Metrics** - vLLM server-side metrics
- 🔄 **Unified View** - Combined client + server correlation
- 🎧 **Audio Metrics** - Audio-specific performance (ASR/translation/chat)

**Navigation**: Use the sidebar to switch between views

**Filters**: Platform, Model, Workload, Core Count, vLLM Version

## Quick Start

```bash
# Launch dashboard
cd automation/test-execution/dashboard-examples/vllm_dashboard
./launch-dashboard.sh

# Open browser to http://localhost:8501

# Navigate using sidebar (←)
```

## Usage

### 1. Run Benchmarks

```bash
# Single test
ansible-playbook llm-benchmark-auto.yml \
  -e "test_model=meta-llama/Llama-3.2-1B-Instruct" \
  -e "workload_type=chat" \
  -e "requested_cores=16"

# Core sweep
ansible-playbook llm-core-sweep-auto.yml \
  -e "test_model=meta-llama/Llama-3.2-1B-Instruct" \
  -e "workload_type=chat" \
  -e "requested_cores_list=[8,16,32,64]"
```

### 2. View Results

1. Open dashboard: `http://localhost:8501`
2. Select a view from sidebar
3. Apply filters as needed
4. Analyze performance

### 3. Navigate

- **Home** - Click "Home" in sidebar
- **Client Metrics** - Click "📊 Client Metrics" in sidebar
- **Server Metrics** - Click "🖥️ Server Metrics" in sidebar
- **Unified View** - Click "🔄 Unified View" in sidebar

## Dashboard Details

### 📊 Client Metrics

**Source**: GuideLLM benchmark results (`benchmarks.json`)

**Metric Families**:
- Throughput (tokens/sec) - mean, P50, P95, P99
- TTFT (ms) - Time To First Token across percentiles
- ITL (ms) - Inter-Token Latency across percentiles
- E2E Latency (s) - End-to-End request latency
- Success Rate (%)
- Efficiency (tokens/sec/core) - managed mode only

**Features**:
- **Multi-percentile overlay**: Select metric family (e.g., TTFT) and view Mean, P50, P95, P99 on the same chart
- **Visual differentiation**: Each percentile uses a distinct line style (solid, dashed, dotted, dash-dot)
- **Configurable X-axis**: Request rate or concurrency
- **Platform comparison**: Side-by-side with % differences for selected percentiles
- **CSV export**: Download filtered data
- **Peak performance summary**: Shows best/peak values for all selected percentiles

**Understanding Percentiles**:

Percentile definition: Pxx = the value below which xx% of data points fall

*Latency percentiles (lower is better)*:
- **P99 = 99% of requests completed within this latency** (worst-case tail)
- High P99 latency = bad (slow tail)
- Example: TTFT P99 = 200ms means 99% of requests got first token within 200ms

*Throughput percentiles (higher is better)*:
- **P99 = 99% of requests achieved this throughput or lower** (upper bound)
- High P99 throughput = good (fast requests)
- Example: Throughput P99 = 100 tok/s means only 1% of requests exceeded 100 tok/s
- **P99 > Mean**: Some fast requests pulled up the average
- **Narrow spread (P99 ≈ P50)**: Consistent per-request throughput

### 🖥️ Server Metrics

**Source**: vLLM Prometheus metrics (`vllm-metrics.json`)

**Metrics**:
- Queue depth (running/waiting)
- CPU cache usage
- Token generation rates
- Request patterns

**Features**:
- Time-series analysis
- Single test or comparison mode
- Summary statistics
- Raw data inspection

### 🔄 Unified View

**Source**: Combined GuideLLM + vLLM metrics

**Analysis**:
- Client-server correlation
- Side-by-side metrics
- Peak performance comparison
- Bottleneck identification

**Use For**:
- Root cause analysis
- Performance validation
- Troubleshooting

### 🎧 Audio Metrics

**Source**: GuideLLM audio benchmark results (`benchmarks.json` + `test-metadata.json`)

**Audio-Specific Metrics**:
- **Audio Throughput** (audio_sec/wall_sec) - How many seconds of audio processed per wall-clock second
- **Real-Time Factor (RTF)** - Processing time / audio duration (< 1.0 = faster than real-time)
- **Request Throughput** (files/sec) - Audio files processed per second
- **Efficiency** - Audio throughput per CPU core

**Metric Families**:
- Audio throughput by stage and model
- RTF percentiles (Mean, P50, P95, P99) - Lower is better
- Latency vs audio duration scaling
- Request throughput comparison
- Per-core efficiency

**Features**:
- **Stage-based analysis**: Sequential, concurrent-N, max-throughput
- **RTF visualization**: Shows if processing is faster/slower than real-time
- **Latency scaling**: How processing time scales with audio length
- **Model comparison**: Compare Whisper tiny/small/medium
- **CSV export**: Download filtered data

**Understanding RTF (Real-Time Factor)**:
- **RTF < 1.0** = Processing faster than real-time ✓ (e.g., RTF=0.1 means 10x faster)
- **RTF = 1.0** = Processing at real-time speed
- **RTF > 1.0** = Processing slower than real-time ⚠️ (e.g., RTF=2.0 means 2x slower)

Example: If RTF=0.2, a 10-second audio clip is processed in 2 seconds.

**Supported Models**:
- Whisper (tiny, small, medium) - ASR transcription
- Ultravox - Audio chat

## Stopping

```bash
./stop-dashboard.sh

# Or kill directly
pkill -f "streamlit.*8501"
```

## Configuration

### Results Directory

Default: `../../../../../results/llm` (relative to pages directory)

Change in sidebar of any dashboard view.

### Filters

All views support:
- Platform
- Model
- Workload
- Core Count
- vLLM Version

Filters apply to the current view only.

## Troubleshooting

### Dashboard won't start

```bash
# Check logs
tail -f /tmp/streamlit-vllm-dashboard.log

# Ensure virtual environment exists
cd ../
./setup.sh
```

### No data showing

1. Verify results directory path
2. Check that benchmarks have been run
3. Look for `benchmarks.json` in results directory

### Navigation not working

- Sidebar should always show navigation links
- Refresh browser if sidebar doesn't appear
- Check that you're running from `Home.py`

## Architecture

```
vllm_dashboard/
├── Home.py                           # Main entry point (run this)
├── pages/
│   ├── 1_📊_Client_Metrics.py       # GuideLLM analysis (LLM models)
│   ├── 2_🖥️_Server_Metrics.py       # vLLM server metrics
│   ├── 3_🔄_Unified_View.py         # Combined view
│   └── 4_🎧_Audio_Metrics.py        # Audio-specific metrics
├── config_manager.py                 # Dashboard configuration
├── launch-dashboard.sh               # Start script
├── stop-dashboard.sh                 # Stop script
└── README.md                         # This file
```
