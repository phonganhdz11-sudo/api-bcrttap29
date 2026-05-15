# apibcr.py
# Flask server chạy trên VPS http://103.159.50.60
# Lấy dữ liệu từ http://103.249.117.228:46565/data, dùng thuật toán Unified Baccarat Predictor
# Endpoint: /sexy/<table_id>  (1-10, C01-C10)

import time
import requests
from flask import Flask, jsonify

app = Flask(__name__)
app.json.sort_keys = False

# ==================== THUẬT TOÁN UNIFIED BACCARAT PREDICTOR ====================
class UnifiedBaccaratPredictor:
    def __init__(self):
        self.history = []  # chuỗi kết quả: 'B', 'P', 'T'

    def add_result(self, result):
        if result not in ('B', 'P', 'T'):
            return False
        self.history.append(result)
        return True

    def get_last_non_tie(self):
        for r in reversed(self.history):
            if r != 'T':
                return r
        return 'B'  # mặc định Banker

    # 1. Streak Following (Theo rồng)
    def calculate_streak_score(self):
        b_streak = p_streak = 0
        for r in reversed(self.history):
            if r == 'B':
                b_streak += 1
            elif r == 'P':
                p_streak += 1
            else:
                break
        max_streak = max(b_streak, p_streak)
        score = min(max_streak * 0.25, 1.0)
        last = self.history[-1] if self.history else 'B'
        return {
            'B': score if last == 'B' else 0,
            'P': score if last == 'P' else 0
        }

    # 2. Chop / Alternation (Theo nhảy)
    def calculate_chop_score(self):
        chop_count = 0
        for i in range(len(self.history)-1, 0, -1):
            curr = self.history[i]
            prev = self.history[i-1]
            if curr != 'T' and prev != 'T' and curr != prev:
                chop_count += 1
            else:
                break
        score = min(chop_count * 0.3, 1.0)
        last_non_tie = self.get_last_non_tie()
        return {
            'B': score if last_non_tie == 'P' else 0,
            'P': score if last_non_tie == 'B' else 0
        }

    # 3. Derived Roads (Big Eye, Small Road, Cockroach) – simplified
    def calculate_derived_roads_score(self):
        non_ties = [r for r in self.history if r != 'T']
        regularity = 0.0
        for i in range(2, len(non_ties)):
            if non_ties[i] == non_ties[i-2]:
                regularity += 0.5
        if non_ties:
            reg_score = min(regularity / (len(non_ties) * 0.4), 1.0)
        else:
            reg_score = 0.0
        last = self.get_last_non_tie()
        if last == 'B':
            return {'B': reg_score, 'P': (1 - reg_score) * 0.6}
        elif last == 'P':
            return {'B': (1 - reg_score) * 0.6, 'P': reg_score}
        else:
            return {'B': reg_score, 'P': (1 - reg_score) * 0.6}

    # 4. Pattern Repetition & Last Column Bias
    def calculate_pattern_score(self):
        last = self.get_last_non_tie()
        scoreB = 0.6 if last == 'B' else 0.4
        scoreP = 0.6 if last == 'P' else 0.4
        recent_ties = self.history[-8:].count('T')
        if recent_ties >= 2:
            scoreB += 0.15
            scoreP += 0.15
        return {'B': scoreB, 'P': scoreP}

    # ==================== DỰ ĐOÁN TỔNG HỢP ====================
    def predict(self):
        if len(self.history) < 5:
            return {
                'recommendation': 'NEUTRAL',
                'confidence': 'YẾU',
                'bankerProb': 50,
                'playerProb': 50,
                'scoreB': 0,
                'scoreP': 0,
                'totalScore': 0,
                'reason': 'Chưa đủ dữ liệu (cần >= 5 kết quả)'
            }

        weight = 25
        scoreB = scoreP = 0.0

        # Gộp điểm từ 4 nhóm thuật toán
        streak = self.calculate_streak_score()
        scoreB += streak['B'] * weight
        scoreP += streak['P'] * weight

        chop = self.calculate_chop_score()
        scoreB += chop['B'] * weight
        scoreP += chop['P'] * weight

        derived = self.calculate_derived_roads_score()
        scoreB += derived['B'] * weight
        scoreP += derived['P'] * weight

        pattern = self.calculate_pattern_score()
        scoreB += pattern['B'] * weight
        scoreP += pattern['P'] * weight

        # House Edge nhẹ cho Banker
        scoreB += 8

        total = scoreB + scoreP
        banker_prob = round((scoreB / total) * 100) if total > 0 else 50
        player_prob = 100 - banker_prob

        diff = abs(scoreB - scoreP)
        if diff > 80:
            confidence = "RẤT MẠNH"
        elif diff > 50:
            confidence = "MẠNH"
        elif diff > 25:
            confidence = "TRUNG BÌNH"
        else:
            confidence = "YẾU"

        recommendation = "Banker" if banker_prob > player_prob else "Player"

        return {
            'recommendation': recommendation,
            'confidence': confidence,
            'bankerProb': banker_prob,
            'playerProb': player_prob,
            'scoreB': round(scoreB),
            'scoreP': round(scoreP),
            'totalScore': round(total)
        }

    def reset(self):
        self.history.clear()


# ==================== GỌI API GỐC & CACHE 2 GIÂY ====================
CACHE = {'data': None, 'timestamp': 0}

def fetch_data():
    if CACHE['data'] is not None and time.time() - CACHE['timestamp'] < 2:
        return CACHE['data']
    try:
        resp = requests.get("http://103.249.117.228:46565/data", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        CACHE['data'] = data
        CACHE['timestamp'] = time.time()
        return data
    except Exception as e:
        print(f"Lỗi khi lấy data: {e}")
        return None


# ==================== ENDPOINT /sexy/<table_id> ====================
@app.route('/sexy/<table_id>')
def sexy_table(table_id):
    data = fetch_data()
    if data is None:
        return jsonify({"error": "Không thể lấy dữ liệu từ nguồn"}), 500

    # Tìm bàn theo table_name
    target = None
    for item in data:
        if item.get('table_name') == table_id:
            target = item
            break
    if target is None:
        return jsonify({"error": f"Không tìm thấy bàn {table_id}"}), 404

    result_str = target.get('result', '')
    if not result_str:
        return jsonify({"error": "Result rỗng"}), 500

    # Nạp lịch sử vào predictor
    predictor = UnifiedBaccaratPredictor()
    for ch in result_str:
        predictor.add_result(ch)

    prediction = predictor.predict()

    # Xây dựng Output
    dudoan_str = prediction['recommendation']

    # Phiên hiện tại
    phien_hien_tai = len(result_str) + 1

    # Phiên trước
    phien = len(result_str)

    # Kết quả ván trước
    ket_qua_van_truoc = result_str[-1] if result_str else ""
    response = {
        "ban": table_id,
        "phien": phien,
        "ket_qua_van_truoc": ket_qua_van_truoc,
        "ket_qua": result_str,
        "phien_hien_tai": phien_hien_tai,
        "du_doan": dudoan_str,
    }
    return jsonify(response)


# ==================== CHẠY SERVER ====================
if __name__ == '__main__':
    # Trên VPS có thể đổi port=80 và debug=False
    import os

app.run(
    host='0.0.0.0',
    port=int(os.environ.get("PORT", 5000)),
    debug=False
)