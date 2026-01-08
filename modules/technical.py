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
            
    # 날짜 데이터 변환 및 인덱스 설정
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
    # 활성화된 전략에 따라 지표 분석 및 ML 데이터 산출
    df = prepare_data(daily_data)
    if df is None or len(df) < 20:
        return {}, "데이터 부족 또는 포맷 오류", []

    signals = []
    summary_data = {
        "price": df['close'].iloc[-1],
        "volume": df['volume'].iloc[-1],
        "rsi": 0.0,
        "ma20_ratio": 0.0,
        "vol_ratio": 0.0,
        "vwap": 0.0
    }

    try:
        # 1. 전략별 시그널 탐지
        if 'ma_cross' in active_strategies:
            if check_ma_cross_strategy(df):
                signals.append("MA5_Cross_MA20")
                
        if 'volume_spike' in active_strategies:
            if check_volume_spike(df):
                signals.append("Volume_Spike")
                
        if 'rsi' in active_strategies:
            rsi_status = check_rsi_strategy(df)
            if rsi_status: signals.append(f"RSI_{rsi_status}")

        if 'vwap' in active_strategies:
            if check_vwap_trend(df):
                signals.append("Price_Above_VWAP")

        # 2. ML 학습용 Feature 계산 (전략 활성화 여부와 관계없이 항상 계산)
        
        # RSI
        rsi_series = calc_rsi(df)
        if rsi_series is not None:
            summary_data['rsi'] = rsi_series.iloc[-1]

        # VWAP
        vwap_series = calc_vwap(df)
        if vwap_series is not None:
            summary_data['vwap'] = vwap_series.iloc[-1]
            
        # MA20 Ratio (이격도: 현재가 / 20일선)
        ma20_series = calc_ma(df, 20)
        if ma20_series is not None:
            ma20_val = ma20_series.iloc[-1]
            if ma20_val and ma20_val != 0:
                summary_data['ma20_ratio'] = summary_data['price'] / ma20_val

        # Volume Ratio (거래량 비율: 현재거래량 / 20일평균거래량)
        vol_sma_series = ta.sma(df['volume'], length=20)
        if vol_sma_series is not None:
            vol_avg = vol_sma_series.iloc[-1]
            if vol_avg and vol_avg != 0:
                summary_data['vol_ratio'] = summary_data['volume'] / vol_avg

    except Exception as e:
        return summary_data, f"전략 계산 중 오류: {e}", signals

    # 요약 텍스트 생성
    summary_text = f"Price: {summary_data['price']}\n"
    summary_text += f"RSI: {summary_data['rsi']:.2f}\n"
    summary_text += f"MA20 Ratio: {summary_data['ma20_ratio']:.2f}\n"
    summary_text += f"Vol Ratio: {summary_data['vol_ratio']:.2f}\n"
    summary_text += f"Signals: {signals}"
    
    summary_data['summary'] = summary_text

    return summary_data, None, signals