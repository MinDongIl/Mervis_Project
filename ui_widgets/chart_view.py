import pandas as pd
import pandas_ta as ta
import numpy as np
import mplfinance as mpf
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel

class RealTimeChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # 정보 라벨
        self.info_label = QLabel("종목을 선택해주세요.")
        self.info_label.setStyleSheet("background-color: #34495E; color: white; font-weight: bold; font-size: 12pt; padding: 5px;")
        self.layout.addWidget(self.info_label)

        # 캔버스 설정
        self.fig = Figure(figsize=(10, 8), dpi=100)
        self.canvas = FigureCanvas(self.fig)
        self.layout.addWidget(self.canvas)
        
        # 스타일 설정
        self.mc = mpf.make_marketcolors(up='red', down='blue', inherit=True)
        self.style = mpf.make_mpf_style(marketcolors=self.mc, gridstyle=':', y_on_right=True)

        self.df = None
        self.current_ticker = None

    def load_data(self, ticker, df, change_rate=0.0):
        self.current_ticker = ticker
        self.df = df
        
        # 전처리
        self.df.columns = [c.capitalize() for c in self.df.columns]
        if 'Volume' not in self.df.columns and 'volume' in self.df.columns:
            self.df.rename(columns={'volume': 'Volume'}, inplace=True)
        self.df.index.name = 'Date'
        
        self.update_plot()
        
        if not self.df.empty:
            last_price = self.df['Close'].iloc[-1]
            self.update_header_info(last_price, change_rate)

    def update_header_info(self, price, change_rate):
        color_code = "#FF0000" if change_rate > 0 else "#0000FF" if change_rate < 0 else "#FFFFFF"
        
        ma_text = ""
        if self.df is not None and not self.df.empty:
            last_row = self.df.iloc[-1]
            ma_vals = []
            for d in [5, 20, 50, 100, 200]:
                col = f'MA{d}'
                if col in self.df.columns and not pd.isna(last_row[col]):
                    ma_vals.append(f"MA{d}:${last_row[col]:,.2f}")
            ma_text = " | ".join(ma_vals)

        self.info_label.setText(
            f"종목: {self.current_ticker} | 현재가: ${price:,.2f} | <span style='color:{color_code}'>등락률: {change_rate:+.2f}%</span><br>"
            f"<span style='font-size:10pt; color:#BDC3C7;'>{ma_text}</span>"
        )

    def calculate_indicators(self):
        if self.df is None or len(self.df) < 5: return

        for length in [5, 20, 50, 100, 200]:
            self.df[f'MA{length}'] = ta.sma(self.df['Close'], length=length)

        is_up = (self.df['High'] > self.df['High'].shift(1)) & \
                (self.df['High'] > self.df['High'].shift(2)) & \
                (self.df['High'] > self.df['High'].shift(-1)) & \
                (self.df['High'] > self.df['High'].shift(-2))
        
        is_down = (self.df['Low'] < self.df['Low'].shift(1)) & \
                  (self.df['Low'] < self.df['Low'].shift(2)) & \
                  (self.df['Low'] < self.df['Low'].shift(-1)) & \
                  (self.df['Low'] < self.df['Low'].shift(-2))

        self.df['Fractal_Up'] = self.df['High'] * 1.01
        self.df['Fractal_Up'] = self.df['Fractal_Up'].where(is_up, np.nan)
        
        self.df['Fractal_Down'] = self.df['Low'] * 0.99
        self.df['Fractal_Down'] = self.df['Fractal_Down'].where(is_down, np.nan)

    def update_plot(self):
        if self.df is None or self.df.empty: return

        self.calculate_indicators()
        self.fig.clear()
        
        # 1. 축(Axes) 먼저 생성
        gs = self.fig.add_gridspec(2, 1, height_ratios=[3, 1])
        ax1 = self.fig.add_subplot(gs[0]) # 메인 차트
        
        has_volume = 'Volume' in self.df.columns and self.df['Volume'].sum() > 0
        ax2 = self.fig.add_subplot(gs[1], sharex=ax1) if has_volume else None # 거래량 차트

        # 2. AddPlots 생성 (panel=0 대신 ax=ax1 사용)
        add_plots = []
        
        # 이동평균선
        ma_settings = [
            (5, 'black', 1.0), (20, 'orange', 1.0), (50, 'blue', 1.0), 
            (100, 'green', 1.0), (200, 'red', 1.0)
        ]
        
        for length, color, width in ma_settings:
            col = f'MA{length}'
            if col in self.df.columns:
                 # panel=0 -> ax=ax1
                 add_plots.append(mpf.make_addplot(self.df[col], color=color, width=width, ax=ax1))

        # 프랙탈
        if 'Fractal_Up' in self.df.columns:
            add_plots.append(mpf.make_addplot(self.df['Fractal_Up'], type='scatter', markersize=50, marker='v', color='blue', ax=ax1))
        if 'Fractal_Down' in self.df.columns:
            add_plots.append(mpf.make_addplot(self.df['Fractal_Down'], type='scatter', markersize=50, marker='^', color='red', ax=ax1))

        try:
            # 3. Plotting
            mpf.plot(
                self.df, 
                type='candle', 
                style=self.style, 
                ax=ax1, 
                volume=ax2, # ax2 객체 직접 전달
                addplot=add_plots if add_plots else None,
                warn_too_much_data=10000
            )
            
            if ax1: ax1.set_ylabel("")
            if ax2: ax2.set_ylabel("")

            self.canvas.draw()
            
        except Exception as e:
            print(f"Plot Error: {e}")

    def update_realtime_price(self, price):
        if self.df is None or self.df.empty: return

        last_idx = self.df.index[-1]
        
        current_h = self.df.at[last_idx, 'High']
        current_l = self.df.at[last_idx, 'Low']
        
        self.df.at[last_idx, 'Close'] = price
        self.df.at[last_idx, 'High'] = max(current_h, price)
        self.df.at[last_idx, 'Low'] = min(current_l, price)
        
        self.update_plot()