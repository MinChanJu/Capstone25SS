import os
import matplotlib.pyplot as plt
from typing import Callable
from Server import Server, calculate_metrics
import numpy as np
import matplotlib
import threading
import json

# macOS에서 한글 폰트 설정 (윈도우는 'Malgun Gothic')
matplotlib.rc('font', family='AppleGothic')
plt.rcParams['axes.unicode_minus'] = False

def round_robin(servers: list[Server]):
  rr_index = [0]
  def inner(_):
    s = servers[rr_index[0] % len(servers)]
    rr_index[0] += 1
    return s
  return inner

def weighted_round_robin(servers: list[Server]):
    weights = [s.bandwidth for s in servers]
    weighted_list = []
    for i, w in enumerate(weights):
        weighted_list.extend([i] * int(w))  # 가중치 비례로 인덱스 복제
    idx = [0]

    def inner(_):
        server = servers[weighted_list[idx[0] % len(weighted_list)]]
        idx[0] += 1
        return server

    return inner

def least_connections(servers: list[Server]):
  return min(servers, key=lambda s: len(s.pending_requests))

def my_optimizer(servers: list[Server]):
  return min(servers, key=lambda s: s.estimate_latency())
  
# 전체 테스트 실행 함수
def run_simulation(servers: list[Server], request_sizes: list[float], requests: list, algorithm: str):
  global algorithm_map
  select_fn: Callable[[list[Server]], Server] = algorithm_map[algorithm]
  if select_fn is None:
    raise ValueError(f"알고리즘 '{algorithm}'이(가) 정의되지 않았습니다.")
  
  # 서버 초기화
  for s in servers:
    s.reset()

  stop_event = threading.Event()

  # 서버별 개별 스레드로 병렬 처리
  threads: list[threading.Thread] = []
  for s in servers:
    t = threading.Thread(target=s.process, args=(stop_event,))
    t.start()
    threads.append(t)

  def send_requests():
    for id, size in enumerate(request_sizes):
      selected = select_fn(servers)
      selected.receive_request(id+1, size)

  request_thread = threading.Thread(target=send_requests)

  request_thread.start()
  request_thread.join()  # 요청 전송 완료 후
  stop_event.set()       # 서버 처리 루프 종료

  for t in threads:
    t.join()
  
  for server in servers:
    result = server.result
    for req_id, server_name, latency, time in result:
      requests[req_id - 1]["algorithm"].append({
        "name": algorithm,
        "server": server_name,
        "latency": latency,
        "time": time
      })
      
  matrix = calculate_metrics(servers)
  summary = [(s.avg_latency(), s.avg_time(), s.total_requests) for s in servers]
  
  return matrix, summary

servers = [
  Server("Server1", 1000),  # 처리 속도: 1000 bytes/sec
  Server("Server2", 800),
  Server("Server3", 900),
  Server("Server4", 700)
]
algorithm_map = {
  "Round Robin": round_robin(servers),
  "Weighted RR": weighted_round_robin(servers),
  "Least Conn": least_connections,
  "Optimized": my_optimizer
}
request_sizes = list(np.random.uniform(500, 1000, 1000))  # 요청 크기(byte)

metainfo = {
  "title": "로드밸런싱 알고리즘 비교",
  "description": "서버별 로드밸런싱 알고리즘의 성능을 비교합니다.",
  "servers": [{"name": s.name, "bandwidth": s.bandwidth} for s in servers],
  "total_request": len(request_sizes),
  "algorithms": list(algorithm_map.keys()),
}

requests = []
for id, req in enumerate(request_sizes):
  requests.append({
    "request_id": id + 1,
    "size": req,
    "algorithm": [],
  })

summary = {}
for algorithm in algorithm_map.keys():
  matrix, result = run_simulation(servers, request_sizes, requests, algorithm)
  average_latency, throughput, fairness_index = matrix
  summary[algorithm] = {
    "average_latency": average_latency,
    "throughput": throughput,
    "fairness_index": fairness_index
  }
  sub = []
  for s, res in zip(servers, result):
    sub.append(
      {
        "server": s.name,
        "bandwidth": s.bandwidth,
        "avg_latency": res[0],
        "avg_time": res[1],
        "total_requests": res[2]
      }
    )
  summary[algorithm]["servers"] = sub

data = {
  "metainfo": metainfo,
  "requests": requests,
  "summary": summary,
}

with open("./result.json", "w", encoding="utf-8") as f:
  json.dump(data, f, ensure_ascii=False, indent=2)

# 결과 출력
text = []
for algorithm, res in summary.items():
  text.append(f"{algorithm}\n응답시간: {res['average_latency']:.3f} sec\n처리량: {res['throughput']:.2f} req/sec\n공정성: {res['fairness_index']:.4f}")
  print(f"{algorithm} = 응답시간: {res['average_latency']:.3f} sec, 처리량: {res['throughput']:.2f} req/sec, 공정성: {res['fairness_index']:.4f}")

# 시각화
x = np.arange(len(servers))
width = 0.2
labels = [f"{s.name}\n처리속도: {s.bandwidth} bytes/sec" for s in servers]

plt.figure(figsize=(14, 7))

bars = []
offsets = np.linspace(-1.5, 1.5, len(summary)) * width
for idx, (algorithm, res) in enumerate(summary.items()):
  bar = plt.bar(x + offsets[idx], [s["avg_latency"] for s in res["servers"]], width, label=algorithm)
  bars.append(bar)

plt.xticks(x, labels)
plt.ylabel("평균 처리 시간 (s)")
plt.title("로드밸런싱 알고리즘 비교")
plt.legend()

for idx in range(len(servers)):
  for bar, data in zip(bars, summary.values()):
    height = bar[idx].get_height()
    plt.text(
      bar[idx].get_x() + bar[idx].get_width()/2,
      height + 0.005,
      f"{data["servers"][idx]["avg_time"]:.2f}s\n{data["servers"][idx]["total_requests"]} req",
      ha='center', va='bottom', fontsize=7
    )
plt.gcf().text(0.7, 0.5, "\n\n".join(text), fontsize=10, bbox=dict(facecolor='white', alpha=0.6))
plt.tight_layout()
i = 1
while os.path.exists(f"./images/try{i}.png"):
    i += 1
filename = f"./images/try{i}.png"
plt.savefig(filename)
plt.close()

print(f"결과 이미지가 {filename}에 저장되었습니다.")