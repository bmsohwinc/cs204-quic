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

