from flask import (
    Flask,
    render_template,
    jsonify,
    request,
    redirect,
    url_for,
    session,
    send_from_directory,
)
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import os
import json
import time
import threading
import firebase_admin
from firebase_admin import credentials, messaging
from datetime import datetime

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
# 로컬(HTTP)과 서버(HTTPS) 환경에 따라 쿠키 보안 설정 자동 분기
# 수정 후: 세션이 브라우저/앱 종료 시 확실히 만료되도록 설정
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False
app.config["SESSION_PERMANENT"] = False  # 세션을 영구 보관하지 않음

app.secret_key = "prime_moving_admin_secure_secret_key_2026"  # 👈 고정 키

DATA_FILE = "nohand_days.txt"
ESTIMATE_FILE = "estimates.txt"
ADMIN_PASSWORD = "admin1234"  # 관리자 비밀번호
TIMEOUT_SECONDS = 300  # 5분 (300초 동안 활동 없으면 완전 로그아웃)

TOKEN_FILE = "admin_tokens.txt"

# --- [Firebase Admin SDK 초기화 및 FCM 푸시 전송 함수] ---
try:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)
except Exception as e:
    print("Firebase Admin 초기화 경고:", e)


def send_fcm_push(title, body):
    """
    백그라운드에서 실행되는 최적화된 FCM 멀티캐스트(배치) 전송 함수
    - 모든 토큰을 한 번의 요청으로 일괄 전송하여 지연 시간 최소화 (0.2초 이내)
    """
    if not os.path.exists(TOKEN_FILE):
        print("토큰 파일이 존재하지 않습니다.")
        return

    tokens = []
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            tokens = json.load(f)
    except Exception as e:
        print("토큰 파일 읽기 에러:", e)
        return

    if not tokens:
        print("등록된 관리자 토큰이 없습니다.")
        return

    print(f"📌 [배치 전송] 대상 관리자 기기 토큰 개수: {len(tokens)}개")

    try:
        # 💡 Firebase 멀티캐스트 메시지 객체 생성 (다중 토큰 일괄 전송)
        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            webpush=messaging.WebpushConfig(
                notification=messaging.WebpushNotification(
                    title=title, body=body, icon="/static/logo-main.png"
                )
            ),
            data={"url": "https://prime-express.duckdns.org/admin"},
            tokens=tokens,
        )

        # 한 번에 일괄 발송 요청
        response = messaging.send_each_for_multicast(message)
        print(f"✨ FCM 일괄 발송 완료! 성공: {response.success_count}건, 실패: {response.failure_count}건")

    except Exception as e:
        print(f"🚨 FCM 일괄 발송 중 예외 발생: {e}")


def load_nohand_days():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print("메모장 파일 읽기 에러:", e)
    return []


def load_estimates():
    if os.path.exists(ESTIMATE_FILE):
        try:
            with open(ESTIMATE_FILE, "r", encoding="utf-8") as f:
                estimates = json.load(f)
                for est in estimates:
                    addr = est.get("userAddress", "")
                    if " / " in addr:
                        parts = addr.split(" / ", 1)
                    elif "/" in addr:
                        parts = addr.split("/", 1)
                    else:
                        parts = [addr, ""]
                    est["departure"] = parts[0].strip()
                    est["arrival"] = parts[1].strip() if len(parts) > 1 else ""
                return estimates
        except Exception:
            return []
    return []


def save_estimate(data):
    estimates = load_estimates()
    data["id"] = len(estimates) + 1
    # 한국 시간(KST, UTC+9) 설정
    KST = timezone(timedelta(hours=9))
    created_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    data["created_at"] = created_at  # 👈 누락되었던 created_at 필드 추가
    data["memo"] = data.get("memo", "")
    estimates.append(data)

    clean_estimates = []
    for est in estimates:
        c_est = est.copy()
        c_est.pop("departure", None)
        c_est.pop("arrival", None)
        clean_estimates.append(c_est)

    with open(ESTIMATE_FILE, "w", encoding="utf-8") as f:
        json.dump(clean_estimates, f, ensure_ascii=False, indent=4)


@app.after_request
def add_header(response):
    # 브라우저 및 모바일이 HTML/정적 파일을 캐시하지 못하도록 원천 차단
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/nohand-days")
def get_nohand_days():
    days_list = load_nohand_days()
    return jsonify({"noHandDays": days_list})


# --- [견적 제출 및 FCM 푸시 알림 라우트] ---
@app.route("/estimate", methods=["POST"])
def submit_estimate():
    print("========================================")
    print("🚀 /estimate 라우트(견적 접수) 진입 성공!")
    print("========================================")
    user_name = request.form.get("userName")
    user_phone = request.form.get("userPhone")
    departure = request.form.get("departure", "").strip()
    arrival = request.form.get("arrival", "").strip()

    if departure or arrival:
        user_address = f"{departure} / {arrival}" if arrival else departure
    else:
        user_address = request.form.get("userAddress", "")
        user_address = user_address.replace("\r\n", " / ").replace("\n", " / ")

    is_storage = request.form.get("isStorageMove") == "on"
    move_date1 = request.form.get("moveDate1")
    move_date2 = request.form.get("moveDate2", "") if is_storage else ""
    visit_date = request.form.get("visitDate", "").strip()  # 💡 선택 입력 처리

    estimate_data = {
        "userName": user_name,
        "userPhone": user_phone,
        "userAddress": user_address,
        "isStorage": is_storage,
        "moveDate1": move_date1,
        "moveDate2": move_date2,
        "visitDate": visit_date,  # 💡 빈 값이면 빈 문자열로 저장
        "memo": "",
    }

    save_estimate(estimate_data)

    # 💡 방문 견적일 유무에 따른 푸시 메시지 동적 구성
    if visit_date:
        push_body = f"고객명: {user_name} ({user_phone}) / 방문견적일: {visit_date} / 이사일: {move_date1}"
    else:
        push_body = f"고객명: {user_name} ({user_phone}) / 이사일: {move_date1}"

    # 💡 [핵심 개선] 알림 발송을 백그라운드 스레드로 분리하여 고객 화면 딜레이 원천 차단 (0초 체감)
    threading.Thread(
        target=send_fcm_push,
        args=("🚨 새로운 이삿짐 견적 접수!", push_body)
    ).start()

    return redirect(url_for("home"))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        password = request.form.get("password")
        if password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            session["last_activity"] = time.time()
            session.permanent = False
            return redirect(url_for("admin_page"))
        else:
            error = "비밀번호가 올바르지 않습니다."
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout", methods=["GET", "POST"])
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin")
def admin_page():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    last_activity = session.get("last_activity", 0)
    current_time = time.time()

    if current_time - last_activity > TIMEOUT_SECONDS:
        session.clear()
        return redirect(url_for("admin_login"))

    session["last_activity"] = current_time

    estimates = load_estimates()
    estimates = sorted(estimates, key=lambda x: x.get("id", 0), reverse=True)

    return render_template("admin.html", estimates=estimates)


@app.route("/admin/update/<int:est_id>", methods=["POST"])
def admin_update(est_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    session["last_activity"] = time.time()

    estimates = load_estimates()
    for est in estimates:
        if est.get("id") == est_id:
            est["userName"] = request.form.get("userName", est["userName"])
            est["userPhone"] = request.form.get("userPhone", est["userPhone"])

            departure = request.form.get("departure", "").strip()
            arrival = request.form.get("arrival", "").strip()
            if departure or arrival:
                est["userAddress"] = (
                    f"{departure} / {arrival}" if arrival else departure
                )
            else:
                address = request.form.get("userAddress", est["userAddress"])
                est["userAddress"] = address.replace("\r\n", " / ").replace("\n", " / ")

            est["moveDate1"] = request.form.get("moveDate1", est["moveDate1"])
            est["visitDate"] = request.form.get(
                "visitDate", ""
            ).strip()  # 💡 방문 견적일 수정 반영 (선택)

            is_storage_val = request.form.get("isStorage") == "on"
            est["isStorage"] = is_storage_val
            if is_storage_val:
                est["moveDate2"] = request.form.get(
                    "moveDate2", est.get("moveDate2", "")
                )
            else:
                est["moveDate2"] = ""

            est["memo"] = request.form.get("memo", "")
            break

    clean_estimates = []
    for est in estimates:
        c_est = est.copy()
        c_est.pop("departure", None)
        c_est.pop("arrival", None)
        clean_estimates.append(c_est)

    with open(ESTIMATE_FILE, "w", encoding="utf-8") as f:
        json.dump(clean_estimates, f, ensure_ascii=False, indent=4)

    return redirect(url_for("admin_page"))


@app.route("/admin/save-token", methods=["POST"])
def save_token():
    data = request.get_json()
    token = data.get("token")
    if token:
        tokens = []
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                try:
                    tokens = json.load(f)
                except:
                    tokens = []
        if token not in tokens:
            tokens.append(token)
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                json.dump(tokens, f, ensure_ascii=False, indent=4)
            print(f"새로운 관리자 기기 토큰 저장됨: {token}")
        return jsonify({"status": "success"})
    return jsonify({"status": "fail"}), 400


@app.route("/sw.js")
def service_worker():
    return send_from_directory(".", "sw.js")


@app.route("/firebase-messaging-sw.js")
def firebase_service_worker():
    return send_from_directory(".", "sw.js")


# -- manifest/json 파일을 읽는 코드
@app.route("/manifest.json")
def serve_manifest():
    return send_from_directory(".", "manifest.json")


@app.route("/admin/delete/<int:est_id>", methods=["POST"])
def admin_delete(est_id):
    # 세션 로그인 여부만 간단히 체크 (타이밍 충돌 방지)
    if not session.get("admin_logged_in"):
        return jsonify({"success": False, "redirect": url_for("admin_login")})

    data = request.get_json() or {}
    password = data.get("delete_password")

    if password != ADMIN_PASSWORD:
        return jsonify({"success": False, "message": "비밀번호가 올바르지 않습니다."})

    estimates = load_estimates()
    estimates = [est for est in estimates if est.get("id") != est_id]

    clean_estimates = []
    for est in estimates:
        c_est = est.copy()
        c_est.pop("departure", None)
        c_est.pop("arrival", None)
        clean_estimates.append(c_est)

    with open(ESTIMATE_FILE, "w", encoding="utf-8") as f:
        json.dump(clean_estimates, f, ensure_ascii=False, indent=4)

    return jsonify({"success": True})


if __name__ == "__main__":
    if not os.path.exists(DATA_FILE):
        from generate_data import generate_lunar_nohand_days

        generate_lunar_nohand_days()

    app.run(host="0.0.0.0", port=5000, debug=False)