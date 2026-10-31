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
from werkzeug.utils import secure_filename

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
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False
app.config["SESSION_PERMANENT"] = False  # 세션을 영구 보관하지 않음

app.secret_key = "prime_moving_admin_secure_secret_key_2026"  # 고정 키

DATA_FILE = "nohand_days.txt"
HOLIDAY_FILE = "holidays.txt"  # 공휴일 파일 상수 추가
ESTIMATE_FILE = "estimates.txt"
ADMIN_PASSWORD = "admin1234"  # 관리자 비밀번호
TIMEOUT_SECONDS = 300  # 5분 (300초 동안 활동 없으면 완전 로그아웃)

TOKEN_FILE = "admin_tokens.txt"

# 💡 이사 후기 데이터 및 업로드 폴더 경로 설정 (.gitignore 대상)
REVIEWS_DATA_DIR = os.path.join(app.root_path, "data")
REVIEWS_UPLOAD_DIR = os.path.join(app.root_path, "static", "uploads", "reviews")
REVIEWS_FILE = os.path.join(REVIEWS_DATA_DIR, "reviews.json")

os.makedirs(REVIEWS_DATA_DIR, exist_ok=True)
os.makedirs(REVIEWS_UPLOAD_DIR, exist_ok=True)

# --- [Firebase Admin SDK 초기화 및 FCM 푸시 전송 함수] ---
try:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)
except Exception as e:
    print("Firebase Admin 초기화 경고:", e)


# 1. 1:1 단건 발송 함수 (토큰 1개당 메시지 1개씩 순회 전송)
def send_fcm_push(title, body):
    TOKEN_FILE = "admin_tokens.txt"
    if not os.path.exists(TOKEN_FILE):
        print("토큰 파일이 존재하지 않습니다.")
        return

    tokens_map = {}
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            content = json.load(f)
            if isinstance(content, dict):
                tokens_map = content
            elif isinstance(content, list):
                tokens_map = {f"legacy_{i}": t for i, t in enumerate(content)}
    except Exception as e:
        print("토큰 파일 읽기 에러:", e)
        return

    if not tokens_map:
        print("등록된 관리자 토큰이 없습니다.")
        return

    tokens_list = list(tokens_map.values())
    print(
        f"📌 [단건 1:1 발송 시작] 대상 관리자 토큰 개수: {len(tokens_list)}개 (최대 5개 제한)"
    )

    success_count = 0
    failure_count = 0

    # 등록된 토큰을 순회하며 각각 단건(1:1) 발송
    for i, token in enumerate(tokens_list):
        try:
            message = messaging.Message(
                data={
                    "title": title,
                    "body": body,
                    "url": "https://prime-express.duckdns.org/admin",
                },
                token=token,
            )

            response = messaging.send(message)
            success_count += 1
            print(f"✨ [발송 성공 {i+1}/{len(tokens_list)}] 토큰: {token[:10]}...")

        except Exception as e:
            failure_count += 1
            print(f"🚨 [발송 실패 {i+1}/{len(tokens_list)}] 에러: {e}")

    print(
        f"✨ FCM 단건 발송 최종 완료! 성공: {success_count}건, 실패: {failure_count}건"
    )


def load_nohand_days():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print("메모장 파일 읽기 에러:", e)
    return []


# 공휴일 파일(.txt)을 읽어오는 함수
def load_holidays():
    if os.path.exists(HOLIDAY_FILE):
        try:
            with open(HOLIDAY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print("공휴일 파일 읽기 에러:", e)
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
    KST = timezone(timedelta(hours=9))
    created_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    data["created_at"] = created_at
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


# 이사 후기 데이터 로드 및 저장 함수
def load_reviews():
    if not os.path.exists(REVIEWS_FILE):
        return []
    try:
        with open(REVIEWS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_reviews(data):
    with open(REVIEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/")
def home():
    reviews = load_reviews()
    return render_template("index.html", reviews=reviews)


@app.route("/api/nohand-days")
def get_nohand_days():
    days_list = load_nohand_days()
    return jsonify({"noHandDays": days_list})


@app.route("/api/holidays")
def get_holidays():
    holidays_list = load_holidays()
    return jsonify({"holidays": holidays_list})


@app.route("/estimate", methods=["POST"])
def submit_estimate():
    print("========================================")
    print("🚀 /estimate 라우트(견적 접수) 진입 성공!")
    print("========================================")

    user_name = request.form.get("userName")
    user_phone = request.form.get("userPhone")

    # 💡 1. 필수 입력값 검증: 이름이나 연락처가 비어있거나 None인 경우 접수 원천 차단
    if (
        not user_name
        or not user_phone
        or str(user_name).strip() == ""
        or str(user_phone).strip() == ""
    ):
        print("🚨 [견적 접수 거부] 필수 입력값(이름 또는 연락처)이 누락되었습니다.")
        return redirect(url_for("home"))

    departure = request.form.get("departure", "").strip()
    arrival = request.form.get("arrival", "").strip()

    if departure or arrival:
        user_address = f"{departure} / {arrival}" if arrival else departure
    else:
        user_address = request.form.get("userAddress", "")
        user_address = user_address.replace("\r\n", " / ").replace("\n", " / ")

    is_storage = request.form.get("isStorageMove") == "on"
    move_date1 = request.form.get("moveDate1")

    # 이사 날짜도 비어있는지 추가 방어 코드
    if not move_date1:
        print("🚨 [견적 접수 거부] 이사 날짜가 누락되었습니다.")
        return redirect(url_for("home"))

    move_date2 = request.form.get("moveDate2", "") if is_storage else ""
    visit_date = request.form.get("visitDate", "").strip()

    estimate_data = {
        "userName": user_name.strip(),
        "userPhone": user_phone.strip(),
        "userAddress": user_address,
        "isStorage": is_storage,
        "moveDate1": move_date1,
        "moveDate2": move_date2,
        "visitDate": visit_date,
        "memo": "",
    }

    save_estimate(estimate_data)

    if visit_date:
        push_body = f"고객명: {user_name} ({user_phone}) / 방문견적일: {visit_date} / 이사일: {move_date1}"
    else:
        push_body = f"고객명: {user_name} ({user_phone}) / 이사일: {move_date1}"

    threading.Thread(
        target=send_fcm_push, args=("🚨 새로운 이삿짐 견적 접수!", push_body)
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


# 관리자 - 이사 후기 관리 페이지 라우트 (별점 평가 저장 로직 반영)
@app.route("/admin/reviews", methods=["GET", "POST"])
def admin_reviews():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    session["last_activity"] = time.time()

    if request.method == "POST":
        titles = request.form.getlist("title")
        regions = request.form.getlist("region")
        contents = request.form.getlist("content")
        ratings = request.form.getlist("rating")  # 💡 별점 데이터 리스트

        existing_reviews = load_reviews()
        updated_reviews = []

        for i in range(len(titles)):
            review_id = i + 1
            review_images = []

            # 💡 기존 이미지가 있다면 유지하되, 체크된 여러 장의 사진을 완벽하게 필터링 및 실제 파일 삭제
            if i < len(existing_reviews):
                old_images = existing_reviews[i].get("images", [])
                delete_target_images = request.form.getlist(f"delete_images_{i}")

                for img_url in old_images:
                    if img_url in delete_target_images:
                        try:
                            relative_path = img_url.lstrip("/")
                            file_path = os.path.join(app.root_path, relative_path)
                            if os.path.exists(file_path):
                                os.remove(file_path)
                        except Exception as e:
                            print("기존 사진 파일 삭제 에러:", e)
                    else:
                        review_images.append(img_url)

            # 새로 업로드된 사진 처리 (멀티 파일)
            files = request.files.getlist(f"images_{i}")
            for file in files:
                if file and file.filename != "":
                    filename = secure_filename(
                        f"rev_{review_id}_{int(time.time())}_{file.filename}"
                    )
                    save_path = os.path.join(REVIEWS_UPLOAD_DIR, filename)
                    file.save(save_path)
                    img_url = f"/static/uploads/reviews/{filename}"
                    review_images.append(img_url)

            # 별점 값 안전하게 파싱 (기본값 5점)
            try:
                rating_val = int(ratings[i]) if i < len(ratings) else 5
            except:
                rating_val = 5

            updated_reviews.append(
                {
                    "id": review_id,
                    "region": regions[i],
                    "title": titles[i],
                    "content": contents[i],
                    "rating": rating_val,  # 💡 별점 저장
                    "images": review_images,
                }
            )

        save_reviews(updated_reviews)
        return redirect(url_for("admin_reviews"))

    reviews = load_reviews()
    # 💡 가장 최근에 등록한 후기(또는 ID가 큰 후기)가 맨 위로 오도록 역순 정렬
    reviews = sorted(reviews, key=lambda x: x.get("id", 0), reverse=True)
    return render_template("admin_reviews.html", reviews=reviews)


# 💡 관리자 - 이사 후기 개별 수정 라우트
@app.route("/admin/reviews/edit/<int:rev_id>", methods=["GET", "POST"])
def admin_reviews_edit(rev_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    session["last_activity"] = time.time()
    reviews = load_reviews()

    target_review = next((r for r in reviews if r.get("id") == rev_id), None)
    if not target_review:
        return redirect(url_for("admin_reviews"))

    if request.method == "POST":
        target_review["region"] = request.form.get("region", "").strip()
        target_review["title"] = request.form.get("title", "").strip()
        target_review["content"] = request.form.get("content", "").strip()
        try:
            target_review["rating"] = int(
                request.form.get("rating", 5)
            )  # 💡 수정 시 별점 반영
        except:
            target_review["rating"] = 5

        save_reviews(reviews)
        return redirect(url_for("admin_reviews"))

    return render_template("admin_review_edit.html", review=target_review)


# 💡 관리자 - 이사 후기 개별 삭제 라우트
@app.route("/admin/reviews/delete/<int:rev_id>", methods=["POST"])
def admin_reviews_delete(rev_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    session["last_activity"] = time.time()

    reviews = load_reviews()
    reviews = [r for r in reviews if r.get("id") != rev_id]

    for idx, r in enumerate(reviews):
        r["id"] = idx + 1

    save_reviews(reviews)
    return redirect(url_for("admin_reviews"))


# 💡 관리자 - 이사 후기 내 특정 사진 개별 삭제 라우트 (비동기 처리)
@app.route("/admin/reviews/delete-image", methods=["POST"])
def admin_reviews_delete_image():
    if not session.get("admin_logged_in"):
        return jsonify({"success": False, "message": "권한이 없습니다."})

    session["last_activity"] = time.time()

    data = request.get_json() or {}
    review_id = data.get("review_id")
    img_url = data.get("img_url", "").strip()

    if not review_id or not img_url:
        return jsonify({"success": False, "message": "잘못된 요청입니다."})

    reviews = load_reviews()
    target_review = next((r for r in reviews if r.get("id") == review_id), None)

    if target_review and "images" in target_review:
        if img_url in target_review["images"]:
            # 데이터 목록에서 제거
            target_review["images"].remove(img_url)
            save_reviews(reviews)

            # 서버 실제 파일 시스템에서 삭제
            try:
                relative_path = img_url.lstrip("/")
                file_path = os.path.join(app.root_path, relative_path)
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                print("사진 파일 실제 삭제 에러:", e)

            return jsonify({"success": True})

    return jsonify({"success": False, "message": "사진을 찾을 수 없습니다."})


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
            est["visitDate"] = request.form.get("visitDate", "").strip()

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
    data = request.json
    token = data.get("token")
    device_id = data.get("device_id", "unknown_device")

    if not token:
        return jsonify({"success": False, "message": "토큰이 없습니다."}), 400

    tokens_map = {}
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                content = json.load(f)
                if isinstance(content, dict):
                    tokens_map = content
                elif isinstance(content, list):
                    tokens_map = {f"legacy_{i}": t for i, t in enumerate(content)}
        except Exception as e:
            print("토큰 파일 읽기 에러:", e)
            tokens_map = {}

    tokens_map = {d: t for d, t in tokens_map.items() if t != token}
    tokens_map[device_id] = token

    if len(tokens_map) > 5:
        excess_keys = list(tokens_map.keys())[:-5]
        for k in excess_keys:
            del tokens_map[k]

    try:
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(tokens_map, f, ensure_ascii=False, indent=4)
        print(
            f"📌 토큰 저장 완료. 현재 유효한 관리자 기기 수: {len(tokens_map)}대 (최대 5개 제한 적용)"
        )
    except Exception as e:
        print("토큰 파일 저장 에러:", e)
        return jsonify({"success": False, "message": "저장 실패"}), 500

    return jsonify({"success": True})


@app.route("/sw.js")
def service_worker():
    return send_from_directory(".", "sw.js")


@app.route("/firebase-messaging-sw.js")
def firebase_service_worker():
    return send_from_directory(".", "sw.js")


@app.route("/manifest.json")
def serve_manifest():
    return send_from_directory(".", "manifest.json")


@app.route("/admin/delete/<int:est_id>", methods=["POST"])
def admin_delete(est_id):
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


# 💡 이용약관 페이지 라우트
@app.route("/terms")
def terms():
    return render_template("terms.html")


# 💡 개인정보처리방침 페이지 라우트
@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


if __name__ == "__main__":
    if not os.path.exists(DATA_FILE) or not os.path.exists(HOLIDAY_FILE):
        from generate_data import generate_lunar_nohand_days, generate_holidays

        if not os.path.exists(DATA_FILE):
            generate_lunar_nohand_days()
        if not os.path.exists(HOLIDAY_FILE):
            generate_holidays()

    app.run(host="0.0.0.0", port=5000, debug=False)
