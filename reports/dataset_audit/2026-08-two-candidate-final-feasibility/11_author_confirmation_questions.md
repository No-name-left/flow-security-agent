# 作者确认问题（未发送）

以下为两封待发送的简洁询问信。本轮未实际发送。

## DataSense: CIC IIoT Dataset 2025

主题：Request for run-level metadata clarification for DataSense

Dear DataSense authors,

We are evaluating DataSense for run-disjoint open-world network intrusion experiments. Could you please clarify:

1. How many independent executions/runs were conducted for each fine-grained attack type?
2. Does one published PCAP correspond to one independent execution? If not, how are PCAP segments related to original executions?
3. Were train/test data divided by run/capture, or after window/row aggregation?
4. Is a run/capture manifest available with run ID, start/end time, attacker, target and fine label?
5. Can network PCAP and network-derived records be used independently from sensor/application logs?
6. How can each derived row/window be traced back to its source PCAP and execution?
7. Can you provide per-class run counts and the number of independent benign capture sessions?

Thank you.

## CICIoMT2024

主题：Request for PCAP-to-run and per-class execution metadata for CICIoMT2024

Dear CICIoMT2024 authors,

We are evaluating CICIoMT2024 for run-disjoint open-world and independent-activity few-shot experiments. Could you please clarify:

1. How many independent executions/runs were conducted for each fine-grained Wi-Fi, MQTT and BLE attack?
2. Does one original PCAP correspond to one independent execution, and how do TCPDUMP chunks relate to that PCAP/run?
3. Are the published train/test directories split by independent run/capture?
4. Is a manifest available with run/capture ID, timestamps, attacker/target/device and fine label?
5. Can the BLE and Wi-Fi/MQTT network captures be used under a common run definition without non-network provenance features?
6. How can each CSV row be traced to its original PCAP, chunk and attack execution?
7. Can you provide per-class PCAP/run counts and a file-level description of benign/profiling sessions?

Thank you.
