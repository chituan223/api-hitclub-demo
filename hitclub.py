import json
import threading
import time
import os
import logging
from urllib.request import urlopen, Request
from flask import Flask, jsonify

# ===================== LOGGING =====================
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ===================== CONFIG =====================
HOST = '0.0.0.0'
POLL_INTERVAL = 5
RETRY_DELAY = 5
MAX_HISTORY = 50

# ===================== LOCKS =====================
lock_101 = threading.Lock()

# ===================== DATA =====================
latest_result_101 = {
    "Phien": 0,
    "Xuc_xac_1": 0,
    "Xuc_xac_2": 0,
    "Xuc_xac_3": 0,
    "Tong": 0,
    "Ket_qua": "Chưa có",
    "id": "daubuoi",
    "Du_doan_tiep": "Đang phân tích...",
    "Do_tin_cay": 0
}

history_101 = []
last_sid_101 = None

# ===================== CORE FUNCTION =====================
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

# ===================== 15 THUẬT TOÁN TÀI/XỈU =================

def algo1_weightedRecent(history):
    if not history: return "Tài"
    t = sum((i+1)/len(history) for i,v in enumerate(history) if v=="Tài")
    x = sum((i+1)/len(history) for i,v in enumerate(history) if v=="Xỉu")
    return "Tài" if t >= x else "Xỉu"

def algo2_expDecay(history, decay=0.6):
    if not history: return "Tài"
    t = x = w = 0; w = 1
    for v in reversed(history):
        if v == "Tài": t += w
        else: x += w
        w *= decay
    return "Tài" if t > x else "Xỉu"

def algo3_longChainReverse(history, k=3):
    if not history: return "Tài"
    last = history[-1]; chain = 1
    for v in reversed(history[:-1]):
        if v == last: chain += 1
        else: break
    return "Xỉu" if chain >= k and last=="Tài" else ("Tài" if chain>=k else last)

def algo4_windowMajority(history, window=5):
    win = history[-window:] if len(history)>=window else history
    if not win: return "Tài"
    return "Tài" if win.count("Tài") >= len(win)/2 else "Xỉu"

def algo5_alternation(history):
    if len(history)<4: return "Tài"
    flips = sum(1 for i in range(1,4) if history[-i]!=history[-i-1])
    return "Xỉu" if flips>=3 and history[-1]=="Tài" else ("Tài" if flips>=3 else history[-1])

def algo6_patternRepeat(history):
    L = len(history)
    if L < 4: return "Tài"
    for length in range(2, min(6, L//2)+1):
        a = "".join(history[-length:])
        b = "".join(history[-2*length:-length])
        if a == b: return history[-length]
    return algo4_windowMajority(history,4)

def algo7_mirror(history):
    if len(history)<8: return history[-1] if history else "Tài"
    return "Xỉu" if history[-4:] == history[-8:-4] and history[-1]=="Tài" else history[-1]

def algo8_entropy(history):
    if not history: return "Tài"
    t = history.count("Tài")
    x = len(history)-t
    diff = abs(t-x)
    if diff <= len(history)//5: return "Xỉu" if history[-1]=="Tài" else "Tài"
    return "Xỉu" if t > x else "Tài"

def algo9_momentum(history):
    if len(history)<2: return "Tài"
    score = sum(1 if history[i]==history[i-1] else -1 for i in range(1,len(history)))
    return history[-1] if score>0 else ("Xỉu" if history[-1]=="Tài" else "Tài")

def algo10_freqRatio(history):
    if not history: return "Tài"
    ratio = history.count("Tài")/len(history)
    if ratio>0.62: return "Xỉu"
    if ratio<0.38: return "Tài"
    return history[-1]

def algo11_parityIndex(history):
    if not history: return "Tài"
    score = 0
    for i,v in enumerate(history):
        if (i%2==0 and v=="Tài") or (i%2==1 and v=="Xỉu"): score+=1
        else: score-=1
    nextEven = len(history)%2==0
    return "Tài" if (score>=0 and nextEven) or (score<0 and not nextEven) else "Xỉu"

def algo12_autocorr(history):
    if len(history)<4: return "Tài"
    sT=sX=0; L=len(history)
    for lag in range(1,min(5,L-1)+1):
        if history[-lag:]==history[-2*lag:-lag]:
            if history[-lag]=="Tài": sT+=1
            else: sX+=1
    if sT>sX: return "Tài"
    if sX>sT: return "Xỉu"
    return history[-1]

def algo13_subwindowMajority(history):
    if len(history)<3: return "Tài"
    votes=[]
    for w in range(3,min(6,len(history))+1):
        win=history[-w:]
        votes.append("Tài" if win.count("Tài")>=len(win)/2 else "Xỉu")
    return "Tài" if votes.count("Tài")>=len(votes)/2 else "Xỉu"

def algo14_runParity(history):
    if not history: return "Tài"
    cur=history[0];length=maxRun=1
    for v in history[1:]:
        if v==cur: length+=1
        else: maxRun=max(maxRun,length);cur=v;length=1
    maxRun=max(maxRun,length)
    return "Xỉu" if maxRun>=4 and history[-1]=="Tài" else history[-1]

def algo15_volatility(history):
    if len(history)<4: return "Tài"
    flips=sum(1 for i in range(1,len(history)) if history[i]!=history[i-1])
    return "Xỉu" if flips/len(history)>0.55 and history[-1]=="Tài" else history[-1]

algos = [algo1_weightedRecent, algo2_expDecay, algo3_longChainReverse, algo4_windowMajority,
         algo5_alternation, algo6_patternRepeat, algo7_mirror, algo8_entropy, algo9_momentum,
         algo10_freqRatio, algo11_parityIndex, algo12_autocorr, algo13_subwindowMajority,
         algo14_runParity, algo15_volatility]

def hybrid15(history):
    if not history: return {"prediction":"Tài","confidence":70,"votes":[]}
    scoreT=scoreX=0
    votes=[]
    for fn in algos:
        v=fn(history)
        votes.append(v)
        if v=="Tài": scoreT+=1
        else: scoreX+=1
    pred="Tài" if scoreT>=scoreX else "Xỉu"
    conf=int((max(scoreT,scoreX)/len(algos))*100)
    return {"prediction":pred,"confidence":conf,"votes":votes}

# ===================== POLLER =====================
def poll_api(lock, result_store, history):
    global last_sid_101
    url = f"https://jakpotgwab.geightdors.net/glms/v1/notify/taixiu?platform_id=g8&gid=vgmn_100"
    while True:
        try:
            req=Request(url, headers={'User-Agent':'Python-Proxy/1.0'})
            with urlopen(req, timeout=10) as resp:
                data=json.loads(resp.read().decode('utf-8'))
                if data.get('status')=='OK' and isinstance(data.get('data'), list):
                    for game in data['data']:
                        cmd=game.get("cmd")
                        if cmd==2006:
                            sid=game.get("sid")
                            d1,d2,d3=game.get("d1"),game.get("d2"),game.get("d3")
                            if sid and sid!=last_sid_101 and None not in (d1,d2,d3):
                                last_sid_101=sid
                                total=d1+d2+d3
                                ket_qua=get_tai_xiu(d1,d2,d3)
                                result={"Phien":sid,"Xuc_xac_1":d1,"Xuc_xac_2":d2,"Xuc_xac_3":d3,
                                        "Tong":total,"Ket_qua":ket_qua,"id":"daubuoi"}
                                update_result(result_store, history, lock, result)
                                hist_results=[h["Ket_qua"] for h in history if h["Ket_qua"] in ("Tài","Xỉu")][::-1]
                                pred=hybrid15(hist_results)
                                result_store["Du_doan_tiep"]=pred["prediction"]
                                result_store["Do_tin_cay"]=pred["confidence"]
                                logger.info(f"Phiên {sid} - Tổng: {total}, KQ: {ket_qua} | Dự đoán: {pred['prediction']} ({pred['confidence']}%)")
        except Exception as e:
            logger.error(f"Lỗi API: {e}")
            time.sleep(RETRY_DELAY)
        time.sleep(POLL_INTERVAL)

# ===================== FLASK =====================
app = Flask(__name__)

@app.route("/api/taixiumd5")
def get_tx_md5():
    with lock_101:
        return jsonify(latest_result_101)

@app.route("/api/history")
def get_hist():
    with lock_101:
        return jsonify({"taixiumd5":history_101})

@app.route("/api/predict")
def predict_next():
    with lock_101:
        history=[h["Ket_qua"] for h in history_101 if h["Ket_qua"] in ("Tài","Xỉu")][::-1]
        res=hybrid15(history)
        return jsonify({"next_prediction":res["prediction"],"confidence":res["confidence"],"votes":res["votes"],"history_len":len(history)})

@app.route("/")
def index():
    return "✅ API Tài Xỉu AI V100 đang chạy | /api/taixiumd5 /api/predict /api/history"

# ===================== MAIN =====================
if __name__=="__main__":
    logger.info("🚀 Khởi động AI Tài Xỉu V100...")
    threading.Thread(target=poll_api, args=(lock_101, latest_result_101, history_101), daemon=True).start()
    port=int(os.environ.get("PORT",8000))
    app.run(host=HOST, port=port)
