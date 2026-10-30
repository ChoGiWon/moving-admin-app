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


# 💡 대한민국 법정 공휴일(양력 고정 및 주요 음력 명절) 생성 함수
def generate_holidays():
    holiday_set = set()
    
    # 2025 ~ 2035년 양력 고정 공휴일 (신정, 삼일절, 어린이날, 현충일, 광복절, 개천절, 한글날, 크리스마스)
    fixed_holidays = [
        (1, 1),   # 신정
        (3, 1),   # 삼일절
        (5, 5),   # 어린이날
        (6, 6),   # 현충일
        (8, 15),  # 광복절
        (10, 3),  # 개천절
        (10, 9),  # 한글날
        (12, 25)  # 크리스마스
    ]
    
    calendar = KoreanLunarCalendar()
    
    for year in range(2025, 2036):
        # 1. 양력 고정 공휴일 추가
        for m, d in fixed_holidays:
            holiday_set.add(f"{year}-{m:02d}-{d:02d}")
            
        # 2. 주요 음력 명절 (설날 연휴 전날, 설날, 다음날 / 추석 전날, 추석, 다음날 / 부처님오신날)
        lunar_events = [
            (1, 1),   # 설날
            (4, 8),   # 부처님오신날
            (8, 15)   # 추석
        ]
        
        for lm, ld in lunar_events:
            try:
                # 음력을 양력으로 변환
                calendar.setLunarDate(year, lm, ld, False)
                solar_year = calendar.solarYear
                solar_month = calendar.solarMonth
                solar_day = calendar.solarDay
                
                lunar_date = datetime(solar_year, solar_month, solar_day)
                
                if lm == 1:  # 설날 (전날~다음날 총 3일)
                    for offset in [-1, 0, 1]:
                        target = lunar_date + timedelta(days=offset)
                        holiday_set.add(target.strftime("%Y-%m-%d"))
                elif lm == 8:  # 추석 (전날~다음날 총 3일)
                    for offset in [-1, 0, 1]:
                        target = lunar_date + timedelta(days=offset)
                        holiday_set.add(target.strftime("%Y-%m-%d"))
                else:  # 부처님오신날 당일
                    holiday_set.add(lunar_date.strftime("%Y-%m-%d"))
            except Exception as e:
                pass

    holidays_list = sorted(list(holiday_set))
    
    file_path = "holidays.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(holidays_list, f, ensure_ascii=False, indent=4)
        
    print(f"✅ 공휴일 생성 완료! 총 {len(holidays_list)}개의 공휴일 데이터가 '{file_path}' 메모장에 성공적으로 저장되었습니다.")


if __name__ == "__main__":
    generate_lunar_nohand_days()
    generate_holidays()