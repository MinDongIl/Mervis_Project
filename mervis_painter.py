import mplfinance as mpf
import pandas as pd
import pandas_ta as ta
import os
import glob
import datetime
import time

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

    # A. [추세선/50일선 전략]
    if 'Trend' in highlight_indicators or 'MA50' in highlight_indicators:
        df['MA50'] = ta.sma(df['Close'], length=50)
        add_plots.append(mpf.make_addplot(df['MA50'], color='blue', width=2.5, panel=0))
        
        df['MA20'] = ta.sma(df['Close'], length=20)
        add_plots.append(mpf.make_addplot(df['MA20'], color='orange', width=0.8, panel=0))

    # B. [일목균형표 전략]
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

    # C. [볼린저 밴드]
    if 'Bollinger' in highlight_indicators:
        bb = ta.bbands(df['Close'], length=20, std=2)
        if bb is not None:
            df['BBU'] = bb[bb.columns[0]] 
            df['BBL'] = bb[bb.columns[2]] 
            add_plots.append(mpf.make_addplot(df['BBU'], panel=0, color='green', linestyle=':', width=1.0))
            add_plots.append(mpf.make_addplot(df['BBL'], panel=0, color='green', linestyle=':', width=1.0))

    # D. [RSI / 다이버전스]
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

    # E. [MACD]
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