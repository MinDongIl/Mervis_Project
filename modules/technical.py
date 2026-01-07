import pandas as pd
import pandas_ta as ta

# 1. 기초 데이터 전처리 함수
def prepare_data(daily_data):
    # API 데이터를 판다스 데이터프레임으로 변환
    if not daily_data: return None
    df = pd.DataFrame(daily_data)
    df = df.rename(columns={'clos': 'close', 'open': 'open', 'high': 'high', 'low': 'low', 'tvol': 'volume', 'xymd': 'date'})
    cols = ['close', 'open', 'high', 'low', 'volume']
    for c in cols: df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df.sort_values('date').reset_index(drop=True)
    return df

# 2. 개별 지표 계산 함수들
def calc_ma(df, length):
    return ta.sma(df['close'], length=length)

def calc_rsi(df, length=14):
    return ta.rsi(df['close'], length=length)

def calc_vwap(df):
    # 일봉 기준 근사치 VWAP
    return ta.vwap(df['high'], df['low'], df['close'], df['volume'])

def calc_bollinger(df, length=20, std=2):
    return ta.bbands(df['close'], length=length, std=std)

# 3. 전략 판단 함수
# 각 함수는 True/False 또는 구체적인 시그널을 반환

def check_ma_cross_strategy(df):
    # 5일선이 20일선을 돌파하는지(골든크로스) 확인
    # 단타용
    if len(df) < 20: return False
    
    ma5 = calc_ma(df, 5)
    ma20 = calc_ma(df, 20)
    
    curr_ma5, prev_ma5 = ma5.iloc[-1], ma5.iloc[-2]
    curr_ma20, prev_ma20 = ma20.iloc[-1], ma20.iloc[-2]
    
    # 어제는 5일선이 20일선 아래, 오늘은 위 -> 골든크로스
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
    curr_rsi = rsi.iloc[-1]
    
    if curr_rsi <= 30: return "OVERSOLD"
    if curr_rsi >= 70: return "OVERBOUGHT"
    return None

def check_vwap_trend(df):
    # 현재가가 VWAP 위에 있는지 확인 (상승 추세)
    vwap = calc_vwap(df)
    if vwap is None: return False
    
    curr_price = df['close'].iloc[-1]
    curr_vwap = vwap.iloc[-1]
    
    if curr_price > curr_vwap:
        return True
    return False

# 4. 통합 실행 함수 (필요한 것만 골라 씀)
def analyze_technical_signals(daily_data, active_strategies):
    # active_strategies: 사용자가 켜놓은 전략 리스트 (예: ['ma_cross', 'rsi'])
    df = prepare_data(daily_data)
    if df is None or len(df) < 60:
        return {}, [], "데이터 부족"

    signals = []
    summary_data = {
        "price": df['close'].iloc[-1],
        "volume": df['volume'].iloc[-1]
    }

    # 사용자가 켜놓은 전략만 실행 (리소스 절약)
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
        # 요약을 위해 계산은 함
        summary_data['rsi'] = calc_rsi(df).iloc[-1]

    if 'vwap' in active_strategies:
        if check_vwap_trend(df):
            signals.append("Price_Above_VWAP")
        summary_data['vwap'] = calc_vwap(df).iloc[-1]

    # 요약 텍스트 생성
    summary_text = f"Price: {summary_data['price']}\n"
    if 'rsi' in summary_data: summary_text += f"RSI: {summary_data['rsi']:.2f}\n"
    if 'vwap' in summary_data: summary_text += f"VWAP: {summary_data['vwap']:.2f}\n"
    summary_text += f"Signals: {signals}"

    return summary_data, None, signals