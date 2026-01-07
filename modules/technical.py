import pandas as pd
import pandas_ta as ta

def prepare_data(daily_data):
    # API 데이터를 판다스 데이터프레임으로 변환
    if not daily_data: return None
    df = pd.DataFrame(daily_data)
    
    # 컬럼명 통일
    rename_map = {'clos': 'close', 'open': 'open', 'high': 'high', 'low': 'low', 'tvol': 'volume', 'xymd': 'date'}
    df = df.rename(columns=rename_map)
    
    cols = ['close', 'open', 'high', 'low', 'volume']
    for c in cols: 
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
            
    # 날짜 데이터 변환 및 인덱스 설정 (지표 계산 필수 조건)
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'].astype(str), format='%Y%m%d', errors='coerce')
        df = df.sort_values('date')
        df.set_index('date', inplace=True)
    else:
        return None

    return df

def calc_ma(df, length):
    return ta.sma(df['close'], length=length)

def calc_rsi(df, length=14):
    return ta.rsi(df['close'], length=length)

def calc_vwap(df):
    try:
        # VWAP 계산
        return ta.vwap(df['high'], df['low'], df['close'], df['volume'])
    except:
        return None

def calc_bollinger(df, length=20, std=2):
    return ta.bbands(df['close'], length=length, std=std)

def check_ma_cross_strategy(df):
    # 5일선이 20일선을 돌파하는지(골든크로스) 확인
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
    # 거래량이 전일 대비 threshold배 이상 폭증했는지 확인
    if len(df) < 2: return False
    curr_vol = df['volume'].iloc[-1]
    prev_vol = df['volume'].iloc[-2]
    
    if prev_vol > 0 and curr_vol >= prev_vol * threshold:
        return True
    return False

def check_rsi_strategy(df):
    # RSI 과매도(30 이하) 또는 과매수(70 이상) 확인
    rsi = calc_rsi(df)
    if rsi is None: return None
    
    curr_rsi = rsi.iloc[-1]
    
    if curr_rsi <= 30: return "OVERSOLD"
    if curr_rsi >= 70: return "OVERBOUGHT"
    return None

def check_vwap_trend(df):
    # 현재가가 VWAP 위에 있는지 확인
    vwap = calc_vwap(df)
    if vwap is None: return False
    
    curr_price = df['close'].iloc[-1]
    curr_vwap = vwap.iloc[-1]
    
    if curr_price > curr_vwap:
        return True
    return False

def analyze_technical_signals(daily_data, active_strategies):
    # 활성화된 전략에 따라 지표 분석 수행
    df = prepare_data(daily_data)
    # 최소 데이터 조건 (이동평균선 계산 등 고려)
    if df is None or len(df) < 20:
        return {}, "데이터 부족 또는 포맷 오류", []

    signals = []
    summary_data = {
        "price": df['close'].iloc[-1],
        "volume": df['volume'].iloc[-1]
    }

    try:
        if 'ma_cross' in active_strategies:
            if check_ma_cross_strategy(df):
                signals.append("MA5_Cross_MA20")
                
        if 'volume_spike' in active_strategies:
            if check_volume_spike(df):
                signals.append("Volume_Spike")
                
        if 'rsi' in active_strategies:
            rsi_status = check_rsi_strategy(df)
            if rsi_status: signals.append(f"RSI_{rsi_status}")
            
            rsi_series = calc_rsi(df)
            if rsi_series is not None:
                summary_data['rsi'] = rsi_series.iloc[-1]

        if 'vwap' in active_strategies:
            if check_vwap_trend(df):
                signals.append("Price_Above_VWAP")
            
            vwap_series = calc_vwap(df)
            if vwap_series is not None:
                summary_data['vwap'] = vwap_series.iloc[-1]
            else:
                summary_data['vwap'] = 0

    except Exception as e:
        return summary_data, f"전략 계산 중 오류: {e}", signals

    # 요약 텍스트 생성
    summary_text = f"Price: {summary_data['price']}\n"
    if 'rsi' in summary_data: summary_text += f"RSI: {summary_data.get('rsi', 0):.2f}\n"
    if 'vwap' in summary_data: summary_text += f"VWAP: {summary_data.get('vwap', 0):.2f}\n"
    summary_text += f"Signals: {signals}"

    return summary_data, None, signals