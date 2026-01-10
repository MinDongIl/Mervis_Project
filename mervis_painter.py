import mplfinance as mpf
import pandas as pd
import pandas_ta as ta
import os
import glob
import datetime
import time
import numpy as np

CHART_DIR = "charts"
if not os.path.exists(CHART_DIR):
    os.makedirs(CHART_DIR)

def clean_old_charts(ticker):
    # 해당 종목의 기존 차트 이미지 삭제 (중복 방지)
    # 패턴: charts/{ticker}_*.png
    search_pattern = os.path.join(CHART_DIR, f"{ticker}_*.png")
    for f in glob.glob(search_pattern):
        try:
            os.remove(f)
        except Exception:
            pass

def draw_chart(ticker, daily_data, highlight_indicators=[]):
    # Brain 요청 지표 시각화 및 파일 저장
    if not daily_data: return None

    # 1. 기존 파일 정리
    clean_old_charts(ticker)

    # 2. 데이터 가공
    df = pd.DataFrame(daily_data)
    df = df.rename(columns={'clos': 'Close', 'open': 'Open', 'high': 'High', 'low': 'Low', 'tvol': 'Volume', 'xymd': 'Date'})
    cols = ['Close', 'Open', 'High', 'Low', 'Volume']
    for c in cols: df[c] = pd.to_numeric(df[c], errors='coerce')
    df['Date'] = pd.to_datetime(df['Date'], format='%Y%m%d')
    df = df.set_index('Date').sort_index()
    
    # 최근 150일 데이터
    df = df.tail(150)

    # 3. AddPlots 리스트 준비
    add_plots = []
    panel_count = 2 # 0:Main, 1:Volume
    
    # ---------------------------------------------------------
    # [전략별 동적 시각화]
    # ---------------------------------------------------------

    # A. [기본 지표: 이동평균선 5종] (항상 표시하거나 옵션으로)
    # 5, 20, 50, 100, 200일선
    # 색상: 5(검정), 20(노랑), 50(파랑), 100(초록), 200(빨강)
    ma_settings = [
        (5, 'black', 1.0),
        (20, 'orange', 1.0),
        (50, 'blue', 1.0),
        (100, 'green', 1.0),
        (200, 'red', 1.0)
    ]
    
    for length, color, width in ma_settings:
        ma_col = f'MA{length}'
        df[ma_col] = ta.sma(df['Close'], length=length)
        # 데이터가 충분치 않아 NaN인 경우 제외
        if not df[ma_col].isnull().all():
            add_plots.append(mpf.make_addplot(df[ma_col], color=color, width=width, panel=0))

    # B. 윌리엄스 프랙탈 (Fractal)
    # 조건에 맞으면 마커 표시 (Up: 파랑 역삼각형 / Down: 빨강 정삼각형)
    if len(df) >= 5:
        # Up Fractal (고점, 매도 시그널)
        is_up = (df['High'] > df['High'].shift(1)) & \
                (df['High'] > df['High'].shift(2)) & \
                (df['High'] > df['High'].shift(-1)) & \
                (df['High'] > df['High'].shift(-2))
        
        # Down Fractal (저점, 매수 시그널)
        is_down = (df['Low'] < df['Low'].shift(1)) & \
                  (df['Low'] < df['Low'].shift(2)) & \
                  (df['Low'] < df['Low'].shift(-1)) & \
                  (df['Low'] < df['Low'].shift(-2))

        # 시각화용 데이터 (캔들보다 약간 위/아래에 찍히도록)
        up_marker = df['High'] * 1.01
        up_marker = up_marker.where(is_up, np.nan)
        
        down_marker = df['Low'] * 0.99
        down_marker = down_marker.where(is_down, np.nan)
        
        # addplot 추가 (markersize 조절 가능)
        add_plots.append(mpf.make_addplot(up_marker, type='scatter', markersize=50, marker='v', color='blue', panel=0))
        add_plots.append(mpf.make_addplot(down_marker, type='scatter', markersize=50, marker='^', color='red', panel=0))

    # C. [일목균형표 전략]
    if 'Ichimoku' in highlight_indicators:
        try:
            ichimoku_df, _ = ta.ichimoku(df['High'], df['Low'], df['Close'])
            if ichimoku_df is not None:
                span_a = ichimoku_df[ichimoku_df.columns[0]] 
                span_b = ichimoku_df[ichimoku_df.columns[1]]
                
                add_plots.append(mpf.make_addplot(span_a, color='green', width=0.1, panel=0))
                add_plots.append(mpf.make_addplot(span_b, color='red', width=0.1, panel=0))
        except:
            pass

    # D. [볼린저 밴드]
    if 'Bollinger' in highlight_indicators:
        bb = ta.bbands(df['Close'], length=20, std=2)
        if bb is not None:
            df['BBU'] = bb[bb.columns[0]] 
            df['BBL'] = bb[bb.columns[2]] 
            add_plots.append(mpf.make_addplot(df['BBU'], panel=0, color='green', linestyle=':', width=1.0))
            add_plots.append(mpf.make_addplot(df['BBL'], panel=0, color='green', linestyle=':', width=1.0))

    # E. [RSI / 다이버전스]
    if 'RSI' in highlight_indicators or 'Divergence' in highlight_indicators:
        df['RSI'] = ta.rsi(df['Close'], length=14)
        add_plots.append(mpf.make_addplot(df['RSI'], panel=panel_count, color='black', ylabel='RSI'))
        add_plots.append(mpf.make_addplot([70]*len(df), panel=panel_count, color='red', linestyle='--', width=0.8))
        add_plots.append(mpf.make_addplot([30]*len(df), panel=panel_count, color='green', linestyle='--', width=0.8))
        
        rsi_buy = df['RSI'].apply(lambda x: x if x <= 30 else float('nan'))
        rsi_sell = df['RSI'].apply(lambda x: x if x >= 70 else float('nan'))
        add_plots.append(mpf.make_addplot(rsi_buy, panel=panel_count, type='scatter', markersize=50, marker='^', color='red'))
        add_plots.append(mpf.make_addplot(rsi_sell, panel=panel_count, type='scatter', markersize=50, marker='v', color='blue'))
        panel_count += 1

    # F. [MACD]
    if 'MACD' in highlight_indicators:
        macd = ta.macd(df['Close'])
        if macd is not None:
            df['MACD'] = macd[macd.columns[0]]
            df['Hist'] = macd[macd.columns[1]]
            df['Signal'] = macd[macd.columns[2]]
            
            add_plots.append(mpf.make_addplot(df['MACD'], panel=panel_count, color='black', ylabel='MACD'))
            add_plots.append(mpf.make_addplot(df['Signal'], panel=panel_count, color='orange'))
            add_plots.append(mpf.make_addplot(df['Hist'], panel=panel_count, type='bar', color='gray', alpha=0.5))
            panel_count += 1

    # ---------------------------------------------------------

    # 4. 스타일 및 저장
    mc = mpf.make_marketcolors(up='red', down='blue', inherit=True)
    s  = mpf.make_mpf_style(marketcolors=mc, gridstyle=':', y_on_right=True)
    
    ratios = (6, 2) + (2,) * (panel_count - 2)
    
    # 타임스탬프를 사용하여 캐싱 방지하되 clean_old_charts로 중복 제거
    filename = f"{ticker}_{int(time.time())}.png"
    filepath = os.path.join(CHART_DIR, filename)

    try:
        reasons = ", ".join(highlight_indicators) if highlight_indicators else "General"
        title_text = f"{ticker} Analysis\nKey Factors: {reasons}"
        
        mpf.plot(
            df, 
            type='candle', 
            style=s, 
            addplot=add_plots,
            volume=True, 
            panel_ratios=ratios,
            title=title_text,
            savefig=dict(fname=filepath, dpi=100, bbox_inches='tight'),
            tight_layout=True,
            warn_too_much_data=10000
        )
        return filepath
    except Exception as e:
        print(f" [Painter Error] {e}")
        return None