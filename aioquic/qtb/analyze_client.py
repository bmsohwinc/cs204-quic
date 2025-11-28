# qtb/analyze_client.py
import os
import nbformat as nbf


def analyze_client(qlog_path: str) -> str:
    """
    Given a single .qlog file, generate a matching .ipynb in the same directory.
    No configs, no directories created.
    """

    qlog_path = os.path.abspath(qlog_path)
    if not os.path.isfile(qlog_path):
        raise FileNotFoundError(f"No such qlog file: {qlog_path}")

    # Derive notebook output path
    base_dir = os.path.dirname(qlog_path)
    base_name = os.path.splitext(os.path.basename(qlog_path))[0]
    notebook_path = os.path.join(base_dir, f"{base_name}.ipynb")

    # Create notebook
    nb = nbf.v4.new_notebook()
    cells = []

    # ---------------------------------------------------------
    # 1. Imports + qlog path
    # ---------------------------------------------------------
    cells.append(nbf.v4.new_code_cell(f"""
import sys
sys.path.append("/workspace")
sys.path
"""))
    
    cells.append(nbf.v4.new_code_cell(f"""
import pandas as pd
import matplotlib.pyplot as plt
from analyze import QLogAnalyzer

QLOG_FILE = r"{qlog_path}"
print("Analyzing:", QLOG_FILE)

qla = QLogAnalyzer(QLOG_FILE)
"""))

    # ---------------------------------------------------------
    # 2. Extract metrics using your analyze.py
    # ---------------------------------------------------------
    cells.append(nbf.v4.new_code_cell("""
cwnd_df = pd.DataFrame(qla.analyze_cwnd())
rtt_df  = pd.DataFrame(qla.analyze_rtt())
loss_df = pd.DataFrame(qla.analyze_loss())
goodput = qla.analyze_goodput()

cwnd_df.head(), rtt_df.head(), loss_df.head(), goodput
"""))

    # ---------------------------------------------------------
    # 3. Normalize time
    # ---------------------------------------------------------
    cells.append(nbf.v4.new_code_cell("""
if not cwnd_df.empty:
    t0 = cwnd_df['time'].iloc[0]
    cwnd_df['time_rel'] = cwnd_df['time'] - t0

if not rtt_df.empty:
    t0 = rtt_df['time'].iloc[0]
    rtt_df['time_rel'] = rtt_df['time'] - t0

loss_df
"""))

    # ---------------------------------------------------------
    # 4. Plot CWND + RTT
    # ---------------------------------------------------------
    cells.append(nbf.v4.new_code_cell("""
plt.figure(figsize=(12,6))

if not cwnd_df.empty:
    plt.plot(cwnd_df['time_rel'], cwnd_df['cwnd'], label="cwnd (bytes)")

if not rtt_df.empty:
    plt.plot(rtt_df['time_rel'], rtt_df['smoothed_rtt'], label="rtt (ms)")

plt.grid(True, alpha=0.3)
plt.legend()
plt.title("CWND + RTT over time")
plt.xlabel("Time (relative)")
plt.show()
"""))

    # ---------------------------------------------------------
    # 5. Summary table
    # ---------------------------------------------------------
    cells.append(nbf.v4.new_code_cell("""
summary = {
    "avg_cwnd": cwnd_df["cwnd"].mean() if not cwnd_df.empty else None,
    "max_cwnd": cwnd_df["cwnd"].max() if not cwnd_df.empty else None,
    "avg_rtt": rtt_df["smoothed_rtt"].mean() if not rtt_df.empty else None,
    "loss_events": len(loss_df),
    "goodput_mbps": goodput["goodput_mbps"],
}

summary
"""))

    nb["cells"] = cells

    with open(notebook_path, "w", encoding="utf-8") as f:
        nbf.write(nb, f)

    print("[qtb] Notebook written:", notebook_path)
    return notebook_path
