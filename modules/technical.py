import pandas as pd
import pandas_ta as ta
import numpy as np

# --- [GUI 차트용 데이터 가공 함수] ---

def process_chart_data(df, settings=None):
    """
    [GUI 전용] Raw DataFrame을 받아 차트 그리기용 데이터로 가공
    """
    if df is None or df.empty:
        return df

    # 1. 컬럼명 표준화 (mplfinance 호환)
    rename_map = {
        'close': 'Close', 'clos': 'Close', 'last': 'Close',
        'open': 'Open',
        'high': 'High',
        'low': 'Low',
        'volume': 'Volume', 'vol': 'Volume', 'tvol': 'Volume', 'acml_vol': 'Volume',
        'date': 'Date', 'xymd': 'Date'
    }
    df.rename(columns=rename_map, inplace=True)
    df.columns = [c.capitalize() if c.lower() in ['close', 'open', 'high', 'low', 'volume', 'date'] else c for c in df.columns]

    if 'Volume' not in df.columns:
        df['Volume'] = 0

    if len(df) < 5:
        return df

    # -----------------------------------------------------------
    # [지표 계산] 
    # -----------------------------------------------------------
    
    # 설정값 로드
    ma_periods = settings.get('ma_periods', [5, 20, 50, 100, 200]) if settings else [5, 20, 50, 100, 200]
    
    # A. 이동평균선 (MA)
    for length in ma_periods:
        try:
            df[f'MA{length}'] = ta.sma(df['Close'], length=length)
        except: pass

    # B. 윌리엄스 프랙탈 (Standard 5-Bar)
    # 좌측 2개, 우측 2개를 비교하는 표준 방식
    try:
        # Up Fractal (고점): N > N-1, N > N-2, N > N+1, N > N+2
        is_up = (df['High'] > df['High'].shift(1)) & \
                (df['High'] > df['High'].shift(2)) & \
                (df['High'] > df['High'].shift(-1)) & \
                (df['High'] > df['High'].shift(-2))
        
        # Down Fractal (저점): N < N-1, N < N-2, N < N+1, N < N+2
        is_down = (df['Low'] < df['Low'].shift(1)) & \
                  (df['Low'] < df['Low'].shift(2)) & \
                  (df['Low'] < df['Low'].shift(-1)) & \
                  (df['Low'] < df['Low'].shift(-2))

        # 차트 시각화용 오프셋 적용
        df['Fractal_Up'] = df['High'] * 1.01
        df['Fractal_Up'] = df['Fractal_Up'].where(is_up, np.nan)
        
        df['Fractal_Down'] = df['Low'] * 0.99
        df['Fractal_Down'] = df['Fractal_Down'].where(is_down, np.nan)
    except: pass

    # C. 볼린저 밴드
    try:
        bb = ta.bbands(df['Close'], length=20, std=2)
        if bb is not None:
            df['BBL'] = bb[bb.columns[0]]
            df['BBM'] = bb[bb.columns[1]]
            df['BBU'] = bb[bb.columns[2]]
    except: pass

    return df

# --- [CLI 및 분석용 데이터 준비 함수] ---

def prepare_data(daily_data):
    if not daily_data: return None
    df = pd.DataFrame(daily_data)
    rename_map = {'clos': 'close', 'open': 'open', 'high': 'high', 'low': 'low', 'tvol': 'volume', 'xymd': 'date'}
    df = df.rename(columns=rename_map)
    cols = ['close', 'open', 'high', 'low', 'volume']
    for c in cols: 
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce')
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'].astype(str), format='%Y%m%d', errors='coerce')
        df = df.sort_values('date')
        df.set_index('date', inplace=True)
    else: return None
    return df

# --- [개별 지표 계산 함수들] ---

def calc_ma(df, length):
    target = 'Close' if 'Close' in df.columns else 'close'
    return ta.sma(df[target], length=length)

def calc_rsi(df, length=14):
    target = 'Close' if 'Close' in df.columns else 'close'
    return ta.rsi(df[target], length=length)

def calc_vwap(df):
    try:
        h = df['High'] if 'High' in df.columns else 'high'
        l = df['Low'] if 'Low' in df.columns else 'low'
        c = df['Close'] if 'Close' in df.columns else 'close'
        v = df['Volume'] if 'Volume' in df.columns else 'volume'
        # pandas_ta vwap는 대소문자 구분을 위해 DataFrame을 직접 넘기거나 컬럼 지정 필요
        # 여기서는 안전하게 컬럼 추출 후 numpy 연산 혹은 ta.vwap 호출
        return ta.vwap(df[h], df[l], df[c], df[v])
    except: return None

def calc_bollinger(df, length=20, std=2):
    target = 'Close' if 'Close' in df.columns else 'close'
    return ta.bbands(df[target], length=length, std=std)

def calc_williams_fractal(df):
    """
    윌리엄스 프랙탈 (표준 5봉 기준) 분석용
    """
    if len(df) < 5: return None, None

    h = df['High'] if 'High' in df.columns else df['high']
    l = df['Low'] if 'Low' in df.columns else df['low']

    # 5봉 기준 로직 (N은 중앙)
    is_up = (h > h.shift(1)) & (h > h.shift(2)) & (h > h.shift(-1)) & (h > h.shift(-2))
    is_down = (l < l.shift(1)) & (l < l.shift(2)) & (l < l.shift(-1)) & (l < l.shift(-2))

    up_fractals = h * 1.01
    down_fractals = l * 0.99
    
    up_fractals = up_fractals.where(is_up, np.nan)
    down_fractals = down_fractals.where(is_down, np.nan)

    return up_fractals, down_fractals

# --- [전략 확인 함수들] ---

def check_ma_cross_strategy(df):
    if len(df) < 20: return False
    ma5 = calc_ma(df, 5)
    ma20 = calc_ma(df, 20)
    if ma5 is None or ma20 is None: return False
    curr_ma5, prev_ma5 = ma5.iloc[-1], ma5.iloc[-2]
    curr_ma20, prev_ma20 = ma20.iloc[-1], ma20.iloc[-2]
    if prev_ma5 < prev_ma20 and curr_ma5 > curr_ma20: return True
    return False

def check_volume_spike(df, threshold=2.0):
    if len(df) < 2: return False
    target_vol = 'Volume' if 'Volume' in df.columns else 'volume'
    curr_vol = df[target_vol].iloc[-1]
    prev_vol = df[target_vol].iloc[-2]
    if prev_vol > 0 and curr_vol >= prev_vol * threshold: return True
    return False

def check_rsi_strategy(df):
    rsi = calc_rsi(df)
    if rsi is None: return None
    curr_rsi = rsi.iloc[-1]
    if curr_rsi <= 30: return "OVERSOLD"
    if curr_rsi >= 70: return "OVERBOUGHT"
    return None

def check_vwap_trend(df):
    vwap = calc_vwap(df)
    if vwap is None: return False
    target_close = 'Close' if 'Close' in df.columns else 'close'
    curr_price = df[target_close].iloc[-1]
    curr_vwap = vwap.iloc[-1]
    if curr_price > curr_vwap: return True
    return False

# --- [Brain용 메인 분석 함수] ---

def analyze_technical_signals(daily_data, active_strategies=[]):
    df = prepare_data(daily_data)
    if df is None or len(df) < 20:
        return {}, "데이터 부족", []

    signals = []
    
    summary_data = {
        "price": df['close'].iloc[-1],
        "volume": df['volume'].iloc[-1],
        "indicators": {}
    }

    try:
        # A. 지표 계산
        for period in [5, 20, 50, 100, 200]:
            summary_data["indicators"][f"ma{period}"] = calc_ma(df, period)

        up_frac, down_frac = calc_williams_fractal(df)
        summary_data["indicators"]["fractal_up"] = up_frac
        summary_data["indicators"]["fractal_down"] = down_frac
        summary_data["indicators"]["rsi"] = calc_rsi(df)
        summary_data["indicators"]["vwap"] = calc_vwap(df)
        
        bb = calc_bollinger(df)
        if bb is not None:
            summary_data["indicators"]["bollinger"] = bb

        # B. 전략 시그널 확인
        if 'ma_cross' in active_strategies and check_ma_cross_strategy(df): 
            signals.append("MA5_Cross_MA20")
        if 'volume_spike' in active_strategies and check_volume_spike(df): 
            signals.append("Volume_Spike")
        if 'rsi' in active_strategies:
            rsi_status = check_rsi_strategy(df)
            if rsi_status: signals.append(f"RSI_{rsi_status}")
        if 'vwap' in active_strategies and check_vwap_trend(df): 
            signals.append("Price_Above_VWAP")
        
        # [프랙탈 시그널 확인]
        # 5봉 프랙탈은 우측 2봉이 완성되어야 하므로, 
        # 가장 최근에 확정될 수 있는 신호는 iloc[-3] (현재 봉 기준 전전날) 입니다.
        if up_frac is not None and len(up_frac) > 3:
            if not np.isnan(up_frac.iloc[-3]): # 2일 전 고점이 프랙탈 고점이었음 (어제,오늘 봉으로 확인됨)
                signals.append("Fractal_Sell_Signal")
            if not np.isnan(down_frac.iloc[-3]):
                signals.append("Fractal_Buy_Signal")

    except Exception as e:
        return summary_data, f"분석 오류: {e}", signals

    rsi_val = summary_data["indicators"]["rsi"].iloc[-1] if summary_data["indicators"].get("rsi") is not None else 0
    summary_data['summary'] = f"Price: {summary_data['price']}\nRSI: {rsi_val:.2f}\nSignals: {signals}"

    return summary_data, None, signals