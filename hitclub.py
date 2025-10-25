import json
import threading
import time
import os
import logging
from urllib.request import urlopen, Request
from flask import Flask, jsonify

# Thiết lập Logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)ss] [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

HOST = '0.0.0.0'
POLL_INTERVAL = 5 # Chu kỳ polling API (giây)
RETRY_DELAY = 5
MAX_HISTORY = 50

# ĐỔI TÊN BIẾN để dễ quản lý (TX cho Tài Xỉu thường, MD5 cho Tài Xỉu MD5)
lock_TX = threading.Lock()
lock_MD5 = threading.Lock()

# Dữ liệu hiện tại cho Tài Xỉu Thường (ID: djtuancon, API: /api/taixiu)
latest_result_TX = {
    "Phien": 0, "Xuc_xac_1": 0, "Xuc_xac_2": 0, "Xuc_xac_3": 0,
    "Tong": 0, "Ket_qua": "Chưa có", "id": "djtuancon",
    "Du_doan_tiep": "Đang phân tích...", "Do_tin_cay": 0
}

# Dữ liệu hiện tại cho Tài Xỉu MD5 (ID: daubuoi, API: /api/taixiumd5)
latest_result_MD5 = {
    "Phien": 0, "Xuc_xac_1": 0, "Xuc_xac_2": 0, "Xuc_xac_3": 0,
    "Tong": 0, "Ket_qua": "Chưa có", "id": "daubuoi",
    "Du_doan_tiep": "Đang phân tích...", "Do_tin_cay": 0
}

history_TX = []
history_MD5 = []

last_sid_TX = None
last_sid_MD5 = None
sid_for_tx = None # Chỉ dùng cho TX thường để bắt SID

# ===================== CORE FUNCTION =====================
def get_tai_xiu(d1, d2, d3):
    """Tính kết quả Tài Xỉu (Xỉu <= 10, Tài > 10)."""
    total = d1 + d2 + d3
    return "Xỉu" if total <= 10 else "Tài"

def update_result(store, history, lock, result):
    """Cập nhật kết quả mới nhất và lịch sử."""
    with lock:
        # Cập nhật các trường cố định
        for key in ["Phien", "Xuc_xac_1", "Xuc_xac_2", "Xuc_xac_3", "Tong", "Ket_qua", "id"]:
            if key in result:
                store[key] = result[key]
        
        # Thêm vào lịch sử (dùng copy để tránh tham chiếu)
        history.insert(0, store.copy()) 
        
        if len(history) > MAX_HISTORY:
            history.pop()

# ===================== 15 THUẬT TOÁN DETERMINISTIC (Giữ nguyên) =====================
# Thuật toán giữ nguyên như bạn cung cấp, chỉ đảm bảo chúng hoạt động với list các chuỗi "Tài" hoặc "Xỉu".
def algo1_weightedRecent(history): #... (code)
    if not history: return "Tài"
    t = sum((i + 1) / len(history) for i, v in enumerate(history) if v == "Tài")
    x = sum((i + 1) / len(history) for i, v in enumerate(history) if v == "Xỉu")
    return "Tài" if t >= x else "Xỉu"
def algo2_expDecay(history, decay=0.6): #... (code)
    if not history: return "Tài"
    t = x = 0; w = 1
    for v in reversed(history):
        if v == "Tài": t += w
        else: x += w
        w *= decay
    return "Tài" if t > x else "Xỉu"
def algo3_longChainReverse(history, k=3): #... (code)
    if not history: return "Tài"
    last = history[-1]
    chain = 1
    for v in reversed(history[:-1]):
        if v == last: chain += 1
        else: break
    # Sửa lỗi logic: Nếu chuỗi dài, dự đoán ngược lại (hoặc theo mặc định nếu chuỗi ngắn)
    return "Xỉu" if chain >= k and last == "Tài" else ("Tài" if chain >= k and last == "Xỉu" else last)
def algo4_windowMajority(history, window=5): #... (code)
    win = history[-window:]
    if not win: return "Tài"
    return "Tài" if win.count("Tài") >= len(win)/2 else "Xỉu"
def algo5_alternation(history): #... (code)
    if len(history) < 4: return "Tài"
    flips = sum(1 for i in range(1,4) if history[-i]!=history[-i-1])
    return "Xỉu" if flips>=3 and history[-1]=="Tài" else ("Tài" if flips>=3 and history[-1]=="Xỉu" else history[-1])
def algo6_patternRepeat(history): #... (code)
    L = len(history)
    if L < 4: return "Tài"
    for length in range(2, min(6, L//2)+1):
        a = "".join(history[-length:])
        b = "".join(history[-2*length:-length])
        if a == b: return history[-length]
    return algo4_windowMajority(history,4)
def algo7_mirror(history): #... (code)
    if len(history) < 8: return history[-1] if history else "Tài"
    return "Xỉu" if history[-4:]==history[-8:-4] and history[-1]=="Tài" else history[-1]
def algo8_entropy(history): #... (code)
    if not history: return "Tài"
    t = history.count("Tài"); x = len(history)-t; diff = abs(t-x)
    # Nếu cân bằng, dự đoán đảo ngược
    if diff <= len(history)//5: return "Xỉu" if history[-1]=="Tài" else "Tài"
    # Nếu mất cân bằng, dự đoán tiếp tục theo bên ít hơn để cân bằng
    return "Xỉu" if t>x else "Tài"
def algo9_volatility(history): #... (code)
    if len(history)<4: return "Tài"
    flips = sum(1 for i in range(1,len(history)) if history[i]!=history[i-1])
    return "Xỉu" if flips/len(history)>0.55 and history[-1]=="Tài" else history[-1]
def algo10_momentum(history): #... (code)
    if len(history)<2: return "Tài"
    score = sum(1 if history[i]==history[i-1] else -1 for i in range(1,len(history)))
    return history[-1] if score>0 else ("Xỉu" if history[-1]=="Tài" else "Tài")
def algo11_parityIndex(history): #... (code)
    if not history: return "Tài"
    score = sum(1 if (i%2==0 and v=="Tài") or (i%2==1 and v=="Xỉu") else -1 for i,v in enumerate(history))
    nextEven = len(history)%2==0
    return "Tài" if score>=0 and nextEven or score<0 and not nextEven else "Xỉu"
def algo12_autocorr(history): #... (code)
    if len(history)<4: return "Tài"
    sT=sX=0; L=len(history)
    for lag in range(1,min(5,L-1)+1):
        if history[-lag:]==history[-2*lag:-lag]:
            if history[-lag]=="Tài": sT+=1
            else: sX+=1
    if sT>sX: return "Tài"
    if sX>sT: return "Xỉu"
    return history[-1]
def algo13_subwindowMajority(history): #... (code)
    if len(history)<3: return "Tài"
    votes=[]
    for w in range(3,min(6,len(history))+1):
        win=history[-w:]
        votes.append("Tài" if win.count("Tài")>=len(win)/2 else "Xỉu")
    return "Tài" if votes.count("Tài")>=len(votes)/2 else "Xỉu"
def algo14_runParity(history): #... (code)
    if not history: return "Tài"
    cur=history[0];length=maxRun=1
    for v in history[1:]:
        if v==cur: length+=1
        else: maxRun=max(maxRun,length);cur=v;length=1
    maxRun=max(maxRun,length)
    return "Xỉu" if maxRun>=4 and history[-1]=="Tài" else history[-1]
def algo15_freqRatio(history): #... (code)
    if not history: return "Tài"
    ratio=history.count("Tài")/len(history)
    if ratio>0.62: return "Xỉu"
    if ratio<0.38: return "Tài"
    return history[-1]

algos = [algo1_weightedRecent, algo2_expDecay, algo3_longChainReverse, algo4_windowMajority,
          algo5_alternation, algo6_patternRepeat, algo7_mirror, algo8_entropy, algo9_volatility,
          algo10_momentum, algo11_parityIndex, algo12_autocorr, algo13_subwindowMajority,
          algo14_runParity, algo15_freqRatio]

def hybrid15(history):
    """Hệ thống bình chọn 15 thuật toán."""
    if not history: return {"prediction":"Tài","confidence":70,"votes":[]}
    scoreT=scoreX=0; votes=[]
    for fn in algos:
        v = fn(history)
        votes.append(v)
        if v=="Tài": scoreT+=1
        else: scoreX+=1
    total_votes = scoreT + scoreX
    pred="Tài" if scoreT>=scoreX else "Xỉu"
    conf=int((max(scoreT,scoreX)/total_votes)*100) if total_votes > 0 else 0
    return {"prediction":pred,"confidence":conf,"votes":votes}

# ===================== API POLLER (Đã sửa lỗi) =====================
def poll_api(gid, lock, result_store, history, is_md5, id_name):
    """
    Polling API và cập nhật kết quả. 
    id_name: dùng để gán ID chính xác (djtuancon/daubuoi)
    """
    global last_sid_TX, last_sid_MD5, sid_for_tx
    
    # Xác định biến SID cuối cùng để tránh lặp lại dữ liệu
    last_sid_ref = last_sid_MD5 if is_md5 else last_sid_TX
    
    url = f"https://jakpotgwab.geightdors.net/glms/v1/notify/taixiu?platform_id=g8&gid={gid}"
    
    while True:
        try:
            req = Request(url, headers={'User-Agent': 'Python-Proxy/1.0'})
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))

            if data.get('status') == 'OK' and isinstance(data.get('data'), list):
                
                # Bắt SID mới nhất cho TX thường (cmd=1008)
                if not is_md5:
                    for game in data['data']:
                        if game.get("cmd") == 1008:
                            sid_for_tx = game.get("sid")
                            logger.info(f"[TX] Đã bắt SID mới: {sid_for_tx}")

                for game in data['data']:
                    cmd = game.get("cmd")

                    # 1. LOGIC CHO TÀI XỈU MD5 (gid=vgmn_100, cmd=2006, is_md5=True)
                    if is_md5 and cmd == 2006:
                        sid = game.get("sid")
                        d1, d2, d3 = game.get("d1"), game.get("d2"), game.get("d3")
                        
                        # Chỉ xử lý nếu có SID mới và xúc xắc đầy đủ
                        if sid and sid != last_sid_ref and None not in (d1, d2, d3):
                            last_sid_MD5 = sid
                            total = d1 + d2 + d3
                            ket_qua = get_tai_xiu(d1, d2, d3)
                            
                            # Cập nhật kết quả cơ bản vào store
                            result = {
                                "Phien": sid, "Xuc_xac_1": d1, "Xuc_xac_2": d2, "Xuc_xac_3": d3,
                                "Tong": total, "Ket_qua": ket_qua, "id": id_name
                            }
                            update_result(result_store, history, lock, result)

                            # Tính dự đoán kế tiếp
                            hist_results = [h["Ket_qua"] for h in history if h["Ket_qua"] in ("Tài","Xỉu")][::-1]
                            pred = hybrid15(hist_results)
                            
                            # Cập nhật dự đoán vào store (TRẢ VỀ ĐẦY ĐỦ NHƯ YÊU CẦU)
                            result_store["Du_doan_tiep"] = pred["prediction"]
                            result_store["Do_tin_cay"] = pred["confidence"]

                            logger.info(f"[MD5] Phiên {sid} - Tổng: {total}, KQ: {ket_qua} | Dự đoán kế: {pred['prediction']} ({pred['confidence']}%)")

                    # 2. LOGIC CHO TÀI XỈU THƯỜNG (gid=vgmn_101, cmd=1003, is_md5=False)
                    elif not is_md5 and cmd == 1003:
                        d1, d2, d3 = game.get("d1"), game.get("d2"), game.get("d3")
                        sid = sid_for_tx # Dùng SID đã bắt được từ cmd 1008
                        
                        if sid and sid != last_sid_ref and None not in (d1, d2, d3):
                            last_sid_TX = sid
                            total = d1 + d2 + d3
                            ket_qua = get_tai_xiu(d1, d2, d3)
                            
                            # Cập nhật kết quả cơ bản vào store
                            result = {
                                "Phien": sid, "Xuc_xac_1": d1, "Xuc_xac_2": d2, "Xuc_xac_3": d3,
                                "Tong": total, "Ket_qua": ket_qua, "id": id_name
                            }
                            update_result(result_store, history, lock, result)
                            
                            # THÊM LOGIC DỰ ĐOÁN CHO TX THƯỜNG (Fix lỗi "ngược")
                            hist_results = [h["Ket_qua"] for h in history if h["Ket_qua"] in ("Tài","Xỉu")][::-1]
                            pred = hybrid15(hist_results)
                            result_store["Du_doan_tiep"] = pred["prediction"]
                            result_store["Do_tin_cay"] = pred["confidence"]

                            logger.info(f"[TX] Phiên {sid} - Tổng: {total}, KQ: {ket_qua} | Dự đoán kế: {pred['prediction']} ({pred['confidence']}%)")
                            
                            sid_for_tx = None # Reset SID sau khi xử lý kết quả

        except Exception as e:
            logger.error(f"Lỗi khi lấy dữ liệu API {gid}: {e}")
            time.sleep(RETRY_DELAY)
            
        time.sleep(POLL_INTERVAL)

# ===================== FLASK API =====================
app = Flask(__name__)

# API Tài Xỉu Thường
@app.route("/api/taixiu")
def get_tx():
    with lock_TX: return jsonify(latest_result_TX)

# API Tài Xỉu MD5 (Trả về đủ Du_doan_tiep và Do_tin_cay)
@app.route("/api/taixiumd5")
def get_tx_md5():
    with lock_MD5: return jsonify(latest_result_MD5)

@app.route("/api/history")
def get_hist():
    with lock_TX, lock_MD5:
        return jsonify({"taixiu": history_TX, "taixiumd5": history_MD5})

@app.route("/api/predict")
def predict_next():
    """Endpoint dự đoán riêng cho MD5 (dùng cho debug)"""
    with lock_MD5:
        history = [h["Ket_qua"] for h in history_MD5 if h["Ket_qua"] in ("Tài","Xỉu")][::-1]
        res = hybrid15(history)
        return jsonify({
            "next_prediction": res["prediction"],
            "confidence": res["confidence"],
            "votes": res["votes"],
            "history_len": len(history)
        })

@app.route("/")
def index():
    return "✅ API Tài Xỉu AI V100 đang chạy | /api/taixiu /api/taixiumd5 /api/predict"

# ===================== MAIN =====================
if __name__ == "__main__":
    logger.info("🚀 Khởi động hệ thống AI Tài Xỉu V100 với Dự đoán tích hợp...")
    
    # ⚙️ TX thường: gid=vgmn_101, id_name=djtuancon, is_md5=False
    threading.Thread(target=poll_api, args=("vgmn_101", lock_TX, latest_result_TX, history_TX, False, "djtuancon"), daemon=True).start()

    # ⚙️ TX MD5: gid=vgmn_100, id_name=daubuoi, is_md5=True (Đảm bảo prediction)
    threading.Thread(target=poll_api, args=("vgmn_100", lock_MD5, latest_result_MD5, history_MD5, True, "daubuoi"), daemon=True).start()
    
    port = int(os.environ.get("PORT", 8000))
    app.run(host=HOST, port=port)
