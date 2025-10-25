import json
import threading
import time
import os
import logging
from urllib.request import urlopen, Request
from flask import Flask, jsonify

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

HOST = '0.0.0.0'
POLL_INTERVAL = 5
RETRY_DELAY = 5
MAX_HISTORY = 50

lock_100 = threading.Lock()
lock_101 = threading.Lock()

latest_result_100 = {"Phien": 0, "Xuc_xac_1": 0, "Xuc_xac_2": 0, "Xuc_xac_3": 0,
                     "Tong": 0, "Ket_qua": "Chưa có", "id": "djtuancon"}
latest_result_101 = {"Phien": 0, "Xuc_xac_1": 0, "Xuc_xac_2": 0, "Xuc_xac_3": 0,
                     "Tong": 0, "Ket_qua": "Chưa có", "id": "daubuoi"}

history_100 = []
history_101 = []

last_sid_100 = None
last_sid_101 = None
sid_for_tx = None

# ===================== CORE FUNCTION =====================
def get_tai_xiu(d1, d2, d3):
    total = d1 + d2 + d3
    return "Xỉu" if total <= 10 else "Tài"

def update_result(store, history, lock, result):
    with lock:
        store.clear()
        store.update(result)
        history.append(result.copy())  # Thêm cuối để giữ thứ tự cũ → mới
        if len(history) > MAX_HISTORY:
            history.pop(0)

# ===================== POLLING API =====================
def poll_api(gid, lock, result_store, history, is_md5):
    global last_sid_100, last_sid_101, sid_for_tx
    url = f"https://jakpotgwab.geightdors.net/glms/v1/notify/taixiu?platform_id=g8&gid={gid}"
    while True:
        try:
            req = Request(url, headers={'User-Agent': 'Python-Proxy/1.0'})
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            if data.get('status') == 'OK' and isinstance(data.get('data'), list):
                for game in data['data']:
                    cmd = game.get("cmd")
                    if not is_md5 and cmd == 1008:
                        sid_for_tx = game.get("sid")
                for game in data['data']:
                    cmd = game.get("cmd")
                    if is_md5 and cmd == 2006:
                        sid = game.get("sid")
                        d1, d2, d3 = game.get("d1"), game.get("d2"), game.get("d3")
                        if sid and sid != last_sid_101 and None not in (d1,d2,d3):
                            last_sid_101 = sid
                            total = d1+d2+d3
                            ket_qua = get_tai_xiu(d1,d2,d3)
                            result = {"Phien": sid, "Xuc_xac_1": d1, "Xuc_xac_2": d2, "Xuc_xac_3": d3,
                                      "Tong": total, "Ket_qua": ket_qua, "id": "daubuoi"}
                            update_result(result_store, history, lock, result)
                            logger.info(f"[MD5] Phiên {sid} - Tổng: {total}, Kết quả: {ket_qua}")
                    elif not is_md5 and cmd == 1003:
                        d1, d2, d3 = game.get("d1"), game.get("d2"), game.get("d3")
                        sid = sid_for_tx
                        if sid and sid != last_sid_100 and None not in (d1,d2,d3):
                            last_sid_100 = sid
                            total = d1+d2+d3
                            ket_qua = get_tai_xiu(d1,d2,d3)
                            result = {"Phien": sid, "Xuc_xac_1": d1, "Xuc_xac_2": d2, "Xuc_xac_3": d3,
                                      "Tong": total, "Ket_qua": ket_qua, "id": "djtuancon"}
                            update_result(result_store, history, lock, result)
                            logger.info(f"[TX] Phiên {sid} - Tổng: {total}, Kết quả: {ket_qua}")
                            sid_for_tx = None
        except Exception as e:
            logger.error(f"Lỗi khi lấy dữ liệu API {gid}: {e}")
            time.sleep(RETRY_DELAY)
        time.sleep(POLL_INTERVAL)

# ================= 10 THUẬT TOÁN DỰ ĐOÁN =================

# 1️⃣ Weighted Recent
def algo_weighted_recent(history):
    if not history: return "Tài"
    t = sum((i+1)/len(history) for i,v in enumerate(history) if v=="Tài")
    x = sum((i+1)/len(history) for i,v in enumerate(history) if v=="Xỉu")
    return "Tài" if t >= x else "Xỉu"

# 2️⃣ Long Chain Reverse
def algo_long_chain_reverse(history, k=3):
    if not history: return "Tài"
    last = history[-1]
    chain = 1
    for v in reversed(history[:-1]):
        if v==last: chain+=1
        else: break
    if chain >= k: return "Xỉu" if last=="Tài" else "Tài"
    return last

# 3️⃣ Run-Length Parity
def algo_run_parity(history):
    if not history: return "Tài"
    cur_val = history[0]
    length = maxRun = 1
    for v in history[1:]:
        if v==cur_val: length+=1
        else:
            maxRun=max(maxRun,length)
            cur_val=v
            length=1
    maxRun=max(maxRun,length)
    return "Xỉu" if maxRun>=4 and history[-1]=="Tài" else history[-1]

# 4️⃣ Window Majority
def algo_window_majority(history, window=5):
    win = history[-window:]
    if not win: return "Tài"
    return "Tài" if win.count("Tài") >= len(win)/2 else "Xỉu"

# 5️⃣ Alternation Detector
def algo_alternation(history):
    if len(history)<4: return "Tài"
    flips = sum(1 for i in range(1,4) if history[-i]!=history[-i-1])
    if flips>=3: return "Xỉu" if history[-1]=="Tài" else "Tài"
    return history[-1]

# 6️⃣ Pattern Repeat Finder
def algo_pattern_repeat(history):
    L=len(history)
    if L<4: return "Tài"
    for length in range(2,min(6,L//2)+1):
        a="".join(history[-length:])
        b="".join(history[-2*length:-length])
        if a==b: return history[-length]
    return algo_window_majority(history,4)

# 7️⃣ Momentum
def algo_momentum(history):
    if len(history)<2: return "Tài"
    score=sum(1 if history[i]==history[i-1] else -1 for i in range(1,len(history)))
    return history[-1] if score>0 else ("Xỉu" if history[-1]=="Tài" else "Tài")

# 8️⃣ Volatility Detector
def algo_volatility(history):
    if len(history)<4: return "Tài"
    flips=sum(1 for i in range(1,len(history)) if history[i]!=history[i-1])
    ratio=flips/len(history)
    return "Xỉu" if ratio>0.55 and history[-1]=="Tài" else history[-1]

# 9️⃣ Entropy Heuristic
def algo_entropy(history):
    if not history: return "Tài"
    t = history.count("Tài")
    x = len(history)-t
    diff = abs(t-x)
    if diff <= len(history)//5: return "Xỉu" if history[-1]=="Tài" else "Tài"
    return "Xỉu" if t>x else "Tài"

# 🔟 Hybrid Voting
def algo_hybrid(history):
    algos = [
        algo_weighted_recent, algo_long_chain_reverse, algo_run_parity,
        algo_window_majority, algo_alternation, algo_pattern_repeat,
        algo_momentum, algo_volatility, algo_entropy
    ]
    votes=[fn(history) for fn in algos]
    scoreT=votes.count("Tài")
    scoreX=votes.count("Xỉu")
    pred="Tài" if scoreT>=scoreX else "Xỉu"
    conf=int(max(scoreT,scoreX)/len(votes)*100)
    return {"prediction":pred,"confidence":conf,"votes":votes}

# ===================== FLASK API =====================
app = Flask(__name__)

@app.route("/api/taixiu")
def get_tx():
    with lock_100:
        return jsonify(latest_result_100)

@app.route("/api/taixiumd5")
def get_tx_md5():
    with lock_101:
        return jsonify(latest_result_101)

@app.route("/api/history")
def get_hist():
    with lock_100, lock_101:
        return jsonify({"taixiu": history_100, "taixiumd5": history_101})

@app.route("/api/predict/tx")
def predict_tx():
    with lock_100:
        history=[h["Ket_qua"] for h in history_100 if h["Ket_qua"] in ("Tài","Xỉu")]
        res=algo_hybrid(history)
        latest=latest_result_100.copy()
        latest["Do_tin_cay"]=res["confidence"]
        latest["Du_doan_tiep"]=res["prediction"]
        return jsonify(latest)

@app.route("/api/predict/md5")
def predict_md5():
    with lock_101:
        history=[h["Ket_qua"] for h in history_101 if h["Ket_qua"] in ("Tài","Xỉu")]
        res=algo_hybrid(history)
        latest=latest_result_101.copy()
        latest["Do_tin_cay"]=res["confidence"]
        latest["Du_doan_tiep"]=res["prediction"]
        return jsonify(latest)

@app.route("/")
def index():
    return ("✅ Tài Xỉu API đang chạy | "
            "/api/taixiu /api/taixiumd5 /api/history /api/predict/tx /api/predict/md5")

# ===================== MAIN =====================
if __name__ == "__main__":
    logger.info("🚀 Khởi động hệ thống API Tài Xỉu AI V100...")
    threading.Thread(target=poll_api, args=("vgmn_100", lock_100, latest_result_100, history_100, False), daemon=True).start()
    threading.Thread(target=poll_api, args=("vgmn_101", lock_101, latest_result_101, history_101, True), daemon=True).start()
    port=int(os.environ.get("PORT",8000))
    app.run(host=HOST, port=port)
