import mplfinance as mpf
import pandas as pd
import pandas_ta as ta
import os
import datetime

CHART_DIR = "charts"
if not os.path.exists(CHART_DIR):
    os.makedirs(CHART_DIR)

def draw_chart(ticker, daily_data, highlight_indicators=[]):
    """
    [만능 화가 모듈]
    Brain이 요청한 모든 보조지표(일목균형표, 추세선, RSI 등)를
    동적으로 차트에 구현하여 시각화합니다.
    """
    if not daily_data: return None

    # 1. 데이터 가공
    df = pd.DataFrame(daily_data)
    df = df.rename(columns={'clos': 'Close', 'open': 'Open', 'high': 'High', 'low': 'Low', 'tvol': 'Volume', 'xymd': 'Date'})
    cols = ['Close', 'Open', 'High', 'Low', 'Volume']
    for c in cols: df[c] = pd.to_numeric(df[c], errors='coerce')
    df['Date'] = pd.to_datetime(df['Date'], format='%Y%m%d')
    df = df.set_index('Date').sort_index()
    
    # 최근 150일 데이터 (일목균형표 선행스팬 표현을 위해 여유 있게)
    df = df.tail(150)

    # 2. AddPlots 리스트 준비
    add_plots = []
    panel_count = 2 # 0:Main, 1:Volume
    
    # ---------------------------------------------------------
    # [전략별 동적 시각화]
    # ---------------------------------------------------------

    # A. [추세선/50일선 전략] (Trendline)
    # 50일선을 아주 굵고 진하게 표시하여 추세 지지/저항을 강조
    if 'Trend' in highlight_indicators or 'MA50' in highlight_indicators:
        df['MA50'] = ta.sma(df['Close'], length=50)
        add_plots.append(mpf.make_addplot(df['MA50'], color='blue', width=2.5, panel=0)) # 굵은 파랑 실선
        # 20일선은 보조로 얇게
        df['MA20'] = ta.sma(df['Close'], length=20)
        add_plots.append(mpf.make_addplot(df['MA20'], color='orange', width=0.8, panel=0))

    # B. [일목균형표 전략] (Ichimoku)
    # 구름대(양운/음운)와 기준선, 전환선을 그림
    if 'Ichimoku' in highlight_indicators:
        # pandas_ta의 ichimoku는 두 개의 dataframe을 반환함
        ichimoku_df, _ = ta.ichimoku(df['High'], df['Low'], df['Close'])
        # 컬럼명은 라이브러리 버전에 따라 다르지만 보통 ISA, ISB, ITS, IKS, ICS 등을 포함
        # 안전하게 컬럼명 매핑 (보통 _9_26_52 접미사가 붙음)
        span_a = ichimoku_df[ichimoku_df.columns[0]] # 선행스팬 1
        span_b = ichimoku_df[ichimoku_df.columns[1]] # 선행스팬 2
        
        # 구름대 채우기 (Fill Between)
        add_plots.append(mpf.make_addplot(span_a, color='green', width=0.1, panel=0))
        add_plots.append(mpf.make_addplot(span_b, color='red', width=0.1, panel=0))
        # *mplfinance의 fill_between 기능은 복잡하므로 선으로 영역 표시

    # C. [볼린저 밴드] (Bollinger)
    if 'Bollinger' in highlight_indicators:
        bb = ta.bbands(df['Close'], length=20, std=2)
        df['BBU'] = bb[bb.columns[0]] # Lower
        df['BBL'] = bb[bb.columns[2]] # Upper
        add_plots.append(mpf.make_addplot(df['BBU'], panel=0, color='green', linestyle=':', width=1.0))
        add_plots.append(mpf.make_addplot(df['BBL'], panel=0, color='green', linestyle=':', width=1.0))

    # D. [RSI / 다이버전스] (Divergence)
    if 'RSI' in highlight_indicators or 'Divergence' in highlight_indicators:
        df['RSI'] = ta.rsi(df['Close'], length=14)
        add_plots.append(mpf.make_addplot(df['RSI'], panel=panel_count, color='black', ylabel='RSI'))
        add_plots.append(mpf.make_addplot([70]*len(df), panel=panel_count, color='red', linestyle='--', width=0.8))
        add_plots.append(mpf.make_addplot([30]*len(df), panel=panel_count, color='green', linestyle='--', width=0.8))
        
        # 과매도/과매수 마킹
        rsi_buy = df['RSI'].apply(lambda x: x if x <= 30 else float('nan'))
        rsi_sell = df['RSI'].apply(lambda x: x if x >= 70 else float('nan'))
        add_plots.append(mpf.make_addplot(rsi_buy, panel=panel_count, type='scatter', markersize=50, marker='^', color='red'))
        add_plots.append(mpf.make_addplot(rsi_sell, panel=panel_count, type='scatter', markersize=50, marker='v', color='blue'))
        panel_count += 1

    # E. [MACD]
    if 'MACD' in highlight_indicators:
        macd = ta.macd(df['Close'])
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
    
    filename = f"{ticker}_{datetime.datetime.now().strftime('%Y%m%d')}.png"
    filepath = os.path.join(CHART_DIR, filename)

    try:
        # 타이틀에 어떤 지표를 사용했는지 명시
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