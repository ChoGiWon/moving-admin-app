import json
from datetime import datetime, timedelta
from korean_lunar_calendar import KoreanLunarCalendar

def generate_lunar_nohand_days():
    calendar = KoreanLunarCalendar()
    no_hand_days = []
    
    start_date = datetime(2025, 1, 1)
    end_date = datetime(2035, 12, 31)
    
    print("⏳ 한국천문연구원 음양력 기준 2025~2035년 손없는 날을 추출 중입니다...")
    
    current = start_date
    while current <= end_date:
        year = current.year
        month = current.month
        day = current.day
        
        # 양력 -> 음력 변환 (한국천문연구원 공식 데이터 기준)
        calendar.setSolarDate(year, month, day)
        lunar_day = calendar.lunarDay
        
        # 음력 날짜 끝자리가 9 또는 0인 날 (9, 10, 19, 20, 29, 30일)
        if lunar_day in [9, 10, 19, 20, 29, 30]:
            date_str = current.strftime("%Y-%m-%d")
            no_hand_days.append(date_str)
            
        current += timedelta(days=1)
        
    no_hand_days.sort()

    file_path = "nohand_days.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(no_hand_days, f, ensure_ascii=False, indent=4)
        
    print(f"✅ 생성 완료! 총 {len(no_hand_days)}개의 손없는 날 데이터가 '{file_path}' 메모장에 성공적으로 저장되었습니다.")

if __name__ == "__main__":
    generate_lunar_nohand_days()