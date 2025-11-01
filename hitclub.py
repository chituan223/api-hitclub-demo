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

latest_result_100 = {
    "Phien": 0, "Xuc_xac_1": 0, "Xuc_xac_2": 0, "Xuc_xac_3": 0,
    "Tong": 0, "Ket_qua": "Chưa có", "id": "tuananhdz",
    "Du_doan_tiep": "Đang phân tích...", "Do_tin_cay": 0
}

latest_result_101 = {
    "Phien": 0, "Xuc_xac_1": 0, "Xuc_xac_2": 0, "Xuc_xac_3": 0,
    "Tong": 0, "Ket_qua": "Chưa có", "id": "tuananhdz",
    "Du_doan_tiep": "Đang phân tích...", "Do_tin_cay": 0
}

history_100 = []
history_101 = []

last_sid_100 = None
last_sid_101 = None
sid_for_tx = None

# ======================================
# 🧠 HÀM CƠ BẢN
# ======================================
def get_tai_xiu(d1, d2, d3):
    total = d1 + d2 + d3
    return "Xỉu" if total <= 10 else "Tài"

def update_result(store, history, lock, result):
    with lock:
        store.clear()
        store.update(result)
        history.insert(0, result.copy())
        if len(history) > MAX_HISTORY:
            history.pop()

# ======================================
# ⚙️ 15 THUẬT TOÁN MỚI
# ======================================
def algo_dynamic_weighted_v3(history):
    if len(history) < 10: return "Tài"
    recent = history[-12:]
    count_tai = recent.count("Tài"); count_xiu = recent.count("Xỉu")
    if all(h == "Tài" for h in recent[-4:]): return "Tài"
    if all(h == "Xỉu" for h in recent[-4:]): return "Xỉu"
    if all(recent[i] != recent[i-1] for i in range(1, 6)):
        return "Tài" if history[-1] == "Xỉu" else "Xỉu"
    last5 = history[-5:]; tai5 = last5.count("Tài"); xiu5 = last5.count("Xỉu")
    if tai5 >= 4: return "Tài"
    if xiu5 >= 4: return "Xỉu"
    weight_tai = (count_tai/12)*0.6 + (tai5/5)*0.4
    weight_xiu = (count_xiu/12)*0.6 + (xiu5/5)*0.4
    if history[-1]=="Tài" and weight_tai>0.7: return "Xỉu"
    if history[-1]=="Xỉu" and weight_xiu>0.7: return "Tài"
    return "Tài" if weight_tai>=weight_xiu else "Xỉu"

def algo_bet_chain(history):
    if len(history) < 5: return "Tài"
    if all(h=="Tài" for h in history[-4:]): return "Tài"
    if all(h=="Xỉu" for h in history[-4:]): return "Xỉu"
    if history[-1]=="Tài" and history[-2]=="Tài": return "Tài"
    if history[-1]=="Xỉu" and history[-2]=="Xỉu": return "Xỉu"
    return "Tài" if history[-1]=="Xỉu" else "Xỉu"

def algo_alternate(history):
    if len(history) < 6: return "Tài"
    flips=sum(1 for i in range(1,6) if history[-i]!=history[-i-1])
    if flips>=4: return "Tài" if history[-1]=="Xỉu" else "Xỉu"
    return history[-1]

def algo_balance_ratio(history):
    if len(history)<10: return "Tài"
    last10 = history[-10:]
    diff = last10.count("Tài") - last10.count("Xỉu")
    if abs(diff) >= 4:
        return "Xỉu" if diff > 0 else "Tài"
    return history[-1]

def algo_smart_reverse(history):
    if len(history)<6: return "Tài"
    tail=history[-6:]
    if tail[-1]==tail[-2]==tail[-3]: return tail[-1]
    if tail[-1]!=tail[-2] and tail[-2]!=tail[-3]:
        return "Tài" if tail[-1]=="Xỉu" else "Xỉu"
    return "Tài" if tail.count("Tài")>=3 else "Xỉu"

def algo_short_weighted(history):
    if len(history)<8: return "Tài"
    tail=history[-8:]
    w_tai=sum(1/(i+1) for i,h in enumerate(reversed(tail)) if h=="Tài")
    w_xiu=sum(1/(i+1) for i,h in enumerate(reversed(tail)) if h=="Xỉu")
    return "Tài" if w_tai>w_xiu else "Xỉu"

def algo_trend_divergence(history):
    if len(history)<7: return "Tài"
    trend=[1 if h=="Tài" else -1 for h in history[-7:]]
    score=sum(trend[-4:])
    if score>=3: return "Tài"
    if score<=-3: return "Xỉu"
    return "Tài" if score>=0 else "Xỉu"

def algo_flip_counter(history):
    if len(history)<6: return "Tài"
    flips=sum(1 for i in range(1,6) if history[-i]!=history[-i-1])
    return "Tài" if flips%2==0 else "Xỉu"

def algo_antistreak(history):
    if len(history)<5: return "Tài"
    if all(h==history[-1] for h in history[-4:]): return history[-1]
    if history[-1]!=history[-2]: return "Tài" if history[-1]=="Xỉu" else "Xỉu"
    return history[-1]

def algo_rolling_prob(history):
    if len(history)<20: return "Tài"
    last20 = history[-20:]
    tai_ratio = last20.count("Tài")/20
    if 0.45 <= tai_ratio <= 0.55:
        return "Tài" if history[-1]=="Xỉu" else "Xỉu"
    return "Tài" if tai_ratio>0.5 else "Xỉu"

def algo_double_swing(history):
    if len(history)<6: return "Tài"
    last6=history[-6:]
    pattern="".join("T" if h=="Tài" else "X" for h in last6)
    if pattern.endswith("TTXX") or pattern.endswith("XXTT"):
        return "Tài" if pattern[-1]=="X" else "Xỉu"
    return "Tài" if last6.count("Tài")>=3 else "Xỉu"

def algo_backward_bet(history):
    if len(history)<7: return "Tài"
    chain=0
    for i in range(1,6):
        if history[-i]==history[-i-1]: chain+=1
        else: break
    if chain>=3: return history[-1]
    return "Tài" if history[-1]=="Xỉu" else "Xỉu"

def algo_triple_layer_trend(history):
    if len(history)<15: return "Tài"
    s1=history[-5:]; s2=history[-10:-5]; s3=history[-15:-10]
    score=sum(s.count("Tài")>2 for s in [s1,s2,s3])
    return "Tài" if score>=2 else "Xỉu"

def algo_double_reverse(history):
    if len(history)<8: return "Tài"
    last8=history[-8:]
    flips=sum(1 for i in range(1,8) if last8[i]!=last8[i-1])
    if flips>=6: return "Tài" if history[-1]=="Xỉu" else "Xỉu"
    return history[-1]

def algo_hybrid_weighted(history):
    if len(history)<10: return "Tài"
    last10=history[-10:]
    weight=sum((1 if h=="Tài" else -1)*(i+1) for i,h in enumerate(reversed(last10)))
    if weight>10: return "Tài"
    if weight<-10: return "Xỉu"
    return "Tài" if weight>=0 else "Xỉu"

# Gộp 15 thuật toán lại
algos = [
    algo_dynamic_weighted_v3, algo_bet_chain, algo_alternate, algo_balance_ratio,
    algo_smart_reverse, algo_short_weighted, algo_trend_divergence, algo_flip_counter,
    algo_antistreak, algo_rolling_prob, algo_double_swing, algo_backward_bet,
    algo_triple_layer_trend, algo_double_reverse, algo_hybrid_weighted
]

# ======================================
# 🧩 Tổng hợp dự đoán (Hybrid)
# ======================================
def hybrid15(history):
    if not history: return {"prediction": "Tài", "confidence": 70, "votes": []}
    scoreT = scoreX = 0
    votes = []
    for fn in algos:
        v = fn(history)
        votes.append(v)
        if v == "Tài": scoreT += 1
        else: scoreX += 1
    pred = "Tài" if scoreT >= scoreX else "Xỉu"
    conf = int((max(scoreT, scoreX) / (scoreT + scoreX)) * 100)
    return {"prediction": pred, "confidence": conf, "votes": votes}

# ======================================
# 🔗 API POLLER
# ======================================
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
                        if sid and sid != last_sid_101 and None not in (d1, d2, d3):
                            last_sid_101 = sid
                            total = d1 + d2 + d3
                            ket_qua = get_tai_xiu(d1, d2, d3)

                            result = {
                                "Phien": sid, "Xuc_xac_1": d1, "Xuc_xac_2": d2, "Xuc_xac_3": d3,
                                "Tong": total, "Ket_qua": ket_qua, "id": "tuananhdz"
                            }
                            update_result(result_store, history, lock, result)

                            hist_results = [h["Ket_qua"] for h in history if h["Ket_qua"] in ("Tài","Xỉu")][::-1]
                            pred = hybrid15(hist_results)
                            result_store["Du_doan_tiep"] = pred["prediction"]
                            result_store["Do_tin_cay"] = pred["confidence"]

                            logger.info(f"[MD5] Phiên {sid} - Tổng {total}, {ket_qua} → Dự đoán kế: {pred['prediction']} ({pred['confidence']}%)")

                    elif not is_md5 and cmd == 1003:
                        d1, d2, d3 = game.get("d1"), game.get("d3"), game.get("d3")
                        sid = sid_for_tx
                        if sid and sid != last_sid_100 and None not in (d1, d2, d3):
                            last_sid_100 = sid
                            total = d1 + d2 + d3
                            ket_qua = get_tai_xiu(d1, d2, d3)
                            result = {
                                "Phien": sid, "Xuc_xac_1": d1, "Xuc_xac_2": d2, "Xuc_xac_3": d3,
                                "Tong": total, "Ket_qua": ket_qua, "id": "tuananhdz"
                            }
                            update_result(result_store, history, lock, result)
                            logger.info(f"[TX] Phiên {sid} - Tổng: {total}, KQ: {ket_qua}")
                            sid_for_tx = None
        except Exception as e:
            logger.error(f"Lỗi lấy dữ liệu API {gid}: {e}")
            time.sleep(RETRY_DELAY)
        time.sleep(POLL_INTERVAL)

# ======================================
# 🌐 FLASK API
# ======================================
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

@app.route("/api/predict")
def predict_next():
    with lock_101:
        history = [h["Ket_qua"] for h in history_101 if h["Ket_qua"] in ("Tài","Xỉu")][::-1]
        res = hybrid15(history)
        return jsonify({
            "next_prediction": res["prediction"],
            "confidence": res["confidence"],
            "votes": res["votes"],
            "history_len": len(history)
        })

@app.route("/")
def index():
    return "✅ API Tài Xỉu AI V101 (tuananhdz) đang chạy | /api/taixiu /api/taixiumd5 /api/predict"

# ======================================
# 🚀 MAIN
# ======================================
if __name__ == "__main__":
    logger.info("🚀 Khởi động hệ thống AI Tài Xỉu V101 với 15 thuật toán mới (tuananhdz)...")
    threading.Thread(target=poll_api, args=("vgmn_101", lock_100, latest_result_100, history_100, False), daemon=True).start()
    threading.Thread(target=poll_api, args=("vgmn_100", lock_101, latest_result_101, history_101, True), daemon=True).start()
    port = int(os.environ.get("PORT", 8000))
    app.run(host=HOST, port=port)
