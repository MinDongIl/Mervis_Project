import pandas as pd
import pandas_ta as ta
import numpy as np

def prepare_data(daily_data):
    if not daily_data: return None
    df = pd.DataFrame(daily_data)
    
    # 컬럼명 통일
    rename_map = {'clos': 'close', 'open': 'open', 'high': 'high', 'low': 'low', 'tvol': 'volume', 'xymd': 'date'}
    df = df.rename(columns=rename_map)
    
    cols = ['close', 'open', 'high', 'low', 'volume']
    for c in cols: 
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
            
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'].astype(str), format='%Y%m%d', errors='coerce')
        df = df.sort_values('date')
        df.set_index('date', inplace=True)
    else:
        return None

    return df

# --- [지표 계산 함수들] ---

def calc_ma(df, length):
    return ta.sma(df['close'], length=length)

def calc_rsi(df, length=14):
    return ta.rsi(df['close'], length=length)

def calc_vwap(df):
    try:
        return ta.vwap(df['high'], df['low'], df['close'], df['volume'])
    except:
        return None

def calc_bollinger(df, length=20, std=2):
    return ta.bbands(df['close'], length=length, std=std)

def calc_williams_fractal(df):
    """
    윌리엄스 프랙탈 (5봉 기준)
    - Up Fractal (매도/저항): 가운데 고가가 좌우 2개 고가보다 높음 (파란색 삼각형 예정)
    - Down Fractal (매수/지지): 가운데 저가가 좌우 2개 저가보다 낮음 (빨간색 삼각형 예정)
    """
    if len(df) < 5: return None, None

    # Pandas shift를 이용한 벡터 연산 (Loop 없음)
    # Up Fractal 조건
    is_up = (df['high'] > df['high'].shift(1)) & \
            (df['high'] > df['high'].shift(2)) & \
            (df['high'] > df['high'].shift(-1)) & \
            (df['high'] > df['high'].shift(-2))

    # Down Fractal 조건
    is_down = (df['low'] < df['low'].shift(1)) & \
              (df['low'] < df['low'].shift(2)) & \
              (df['low'] < df['low'].shift(-1)) & \
              (df['low'] < df['low'].shift(-2))

    # 차트 시각화를 위해 캔들 고가/저가보다 약간 떨어뜨려 값 설정 (Offset)
    up_fractals = df['high'] * 1.01   # 고가보다 1% 위
    down_fractals = df['low'] * 0.99  # 저가보다 1% 아래
    
    # 조건 만족 안 하는 곳은 NaN 처리
    up_fractals = up_fractals.where(is_up, np.nan)
    down_fractals = down_fractals.where(is_down, np.nan)

    return up_fractals, down_fractals

# --- [전략 확인 함수들 (기존 유지)] ---

def check_ma_cross_strategy(df):
    # 5일선이 20일선을 돌파(골든크로스) 확인
    if len(df) < 20: return False
    ma5 = calc_ma(df, 5)
    ma20 = calc_ma(df, 20)
    if ma5 is None or ma20 is None: return False

    curr_ma5, prev_ma5 = ma5.iloc[-1], ma5.iloc[-2]
    curr_ma20, prev_ma20 = ma20.iloc[-1], ma20.iloc[-2]
    
    if prev_ma5 < prev_ma20 and curr_ma5 > curr_ma20:
        return True
    return False

def check_volume_spike(df, threshold=2.0):
    # 거래량 폭증 확인
    if len(df) < 2: return False
    curr_vol = df['volume'].iloc[-1]
    prev_vol = df['volume'].iloc[-2]
    if prev_vol > 0 and curr_vol >= prev_vol * threshold:
        return True
    return False

def check_rsi_strategy(df):
    # RSI 과매수/과매도 확인
    rsi = calc_rsi(df)
    if rsi is None: return None
    curr_rsi = rsi.iloc[-1]
    if curr_rsi <= 30: return "OVERSOLD"
    if curr_rsi >= 70: return "OVERBOUGHT"
    return None

def check_vwap_trend(df):
    # VWAP 위 가격 확인
    vwap = calc_vwap(df)
    if vwap is None: return False
    curr_price = df['close'].iloc[-1]
    curr_vwap = vwap.iloc[-1]
    if curr_price > curr_vwap:
        return True
    return False

# --- [메인 분석 함수] ---

def analyze_technical_signals(daily_data, active_strategies=[]):
    """
    차트 시각화용 지표 데이터(indicators)와
    매매 전략 시그널(signals)을 모두 반환
    """
    df = prepare_data(daily_data)
    if df is None or len(df) < 20:
        return {}, "데이터 부족 또는 포맷 오류", []

    signals = []
    
    # 1. 시각화 및 정보용 데이터 구조
    summary_data = {
        "price": df['close'].iloc[-1],
        "volume": df['volume'].iloc[-1],
        "indicators": {} # 차트에 그릴 라인/점 데이터들
    }

    try:
        # --- A. 지표 계산 (차트용) ---
        
        # 1. 이동평균선 5개 (5, 20, 50, 100, 200)
        for period in [5, 20, 50, 100, 200]:
            summary_data["indicators"][f"ma{period}"] = calc_ma(df, period)

        # 2. 윌리엄스 프랙탈
        up_frac, down_frac = calc_williams_fractal(df)
        summary_data["indicators"]["fractal_up"] = up_frac
        summary_data["indicators"]["fractal_down"] = down_frac

        # 3. RSI & VWAP
        summary_data["indicators"]["rsi"] = calc_rsi(df)
        summary_data["indicators"]["vwap"] = calc_vwap(df)
        
        # 4. 볼린저 밴드
        bb = calc_bollinger(df)
        if bb is not None:
            # pandas_ta는 BBL(하단), BBM(중단), BBU(상단) 등의 이름으로 반환됨
            summary_data["indicators"]["bollinger"] = bb

        # --- B. 전략 시그널 확인 (알림용) ---
        
        # 1. 기존 전략들
        if 'ma_cross' in active_strategies:
            if check_ma_cross_strategy(df): 
                signals.append("MA5_Cross_MA20")
                
        if 'volume_spike' in active_strategies:
            if check_volume_spike(df): 
                signals.append("Volume_Spike")
                
        if 'rsi' in active_strategies:
            rsi_status = check_rsi_strategy(df)
            if rsi_status: 
                signals.append(f"RSI_{rsi_status}")

        if 'vwap' in active_strategies:
            if check_vwap_trend(df): 
                signals.append("Price_Above_VWAP")
        
        # 2. 신규 프랙탈 시그널 (최근 3일 내 발생 여부)
        # 프랙탈은 미래 2개 봉이 필요하므로, 확정된 가장 최신 신호는 2일 전 데이터임
        if up_frac is not None and len(up_frac) > 3:
            if not np.isnan(up_frac.iloc[-3]):
                signals.append("Fractal_Sell_Signal")
            if not np.isnan(down_frac.iloc[-3]):
                signals.append("Fractal_Buy_Signal")

    except Exception as e:
        return summary_data, f"분석 오류: {e}", signals

    # 텍스트 요약 생성
    rsi_val = summary_data["indicators"]["rsi"].iloc[-1] if summary_data["indicators"].get("rsi") is not None else 0
    
    summary_text = f"Price: {summary_data['price']}\n"
    summary_text += f"RSI: {rsi_val:.2f}\n"
    summary_text += f"Signals: {signals}"
    
    summary_data['summary'] = summary_text

    return summary_data, None, signals