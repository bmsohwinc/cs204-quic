import argparse
import json
import logging
import os
from typing import TypedDict, List, Dict, Any

import pandas as pd

from aioquic.quic.logger import QuicLoggerTrace

logger = logging.getLogger()

class QlogDict(TypedDict):
    qlog_format: str
    qlog_version: str
    traces: list[QuicLoggerTrace]


class QLogAnalyzer():
    def __init__(self, log_path: str):
        self.log_path: str = log_path
        self.log_id: str = ""
        self.log_data: QlogDict = None
        self._read_log_file()

    def analyze_cwnd(self) -> list[dict]:
        cwnd_data = []
        for trace in self.log_data.get("traces", []):
            for event in trace["events"]:
                if event["name"] == "recovery:metrics_updated":
                    cwnd_data.append({
                        "cwnd": event["data"]["cwnd"],
                        "bytes_in_flight": event["data"]["bytes_in_flight"],
                        "time": event["time"]
                    })

        self._save_to_csv("cwnd", cwnd_data)
        return cwnd_data
    
    def analyze_rtt(self) -> list[dict]:
        rtt_data = []
        for trace in self.log_data.get("traces", []):
            for event in trace["events"]:
                if event["name"] == "recovery:metrics_updated":
                    data = event["data"]
                    rtt_data.append({
                        "time": event["time"],
                        "min_rtt":     data.get("min_rtt"),
                        "smoothed_rtt": data.get("smoothed_rtt"),
                        "latest_rtt":   data.get("latest_rtt"),
                        "rtt_variance": data.get("rtt_variance"),
                    })

        self._save_to_csv("rtt", rtt_data)
        return rtt_data
    
    def analyze_loss(self) -> list[dict]:
        loss_events = [] 
        for trace in self.log_data.get("traces", []):
            for event in trace["events"]:
                if event["name"] == "recovery:packet_lost":
                    data = event["data"]
                    loss_events.append({
                        "time": event["time"],
                        "packet_number": data.get("packet_number"),
                        "packet_type": data.get("packet_type"),
                        "trigger": data.get("trigger"),
                    })

        self._save_to_csv("loss", loss_events)
        return loss_events
    
    def analyze_goodput(self):
        total_bytes = 0
        t_first = None
        t_last = None

        for trace in self.log_data["traces"]:
            for ev in trace["events"]:
                t = ev["time"]

                # keep track of active duration
                if t_first is None:
                    t_first = t
                t_last = t

                if ev["name"] == "http:frame_parsed":
                    frame = ev["data"].get("frame", {})
                    if frame.get("frame_type") == "data":
                        total_bytes += ev["data"].get("length", 0)

        if t_first is None or t_last is None:
            return {"bytes": 0, "duration": 0.0, "goodput_mbps": 0.0}

        duration_sec = (t_last - t_first) / 1000.0  # qlog time is in ms
        goodput_mbps = (total_bytes * 8) / (duration_sec * 1e6)

        return {
            "bytes": total_bytes,
            "duration": duration_sec,
            "goodput_mbps": goodput_mbps,
        }


    def _read_log_file(self):
        if not self.log_path:
            raise Exception("log_path is None")
        
        with open(self.log_path, "r", encoding="utf-8") as f:
            self.log_data = json.load(f)
    
    def _save_to_csv(self, keyword, data: list[dict]):
        directory, filename = os.path.split(self.log_path)

        target_path = f"{directory}/{filename[:-5]}_{keyword}.csv"

        df = pd.DataFrame(data)
        df.to_csv(target_path, index=False)


def main():
    parser = argparse.ArgumentParser(description="Process a file path.")
    parser.add_argument("filepath", type=str, help="Path to the input file")

    args = parser.parse_args()

    qla = QLogAnalyzer(args.filepath)

    qla.analyze_cwnd()

if __name__ == "__main__":
    main()

