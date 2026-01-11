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
        
        # 상단 정보 표시 라벨
        self.info_label = QLabel("종목을 선택해주세요.")
        self.info_label.setStyleSheet("background-color: #34495E; color: white; font-weight: bold; font-size: 12pt; padding: 5px;")
        self.layout.addWidget(self.info_label)

        # 캔버스 설정
        self.fig = Figure(figsize=(10, 6), dpi=100)
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.fig.patch.set_facecolor('#F0F8FF')
        
        self.layout.addWidget(self.canvas)
        
        # 기본 스타일 설정
        self.mc = mpf.make_marketcolors(up='red', down='blue', inherit=True)
        self.style = mpf.make_mpf_style(marketcolors=self.mc, gridstyle=':', y_on_right=True)

        self.df = None
        self.current_ticker = None
        self.current_change_rate = 0.0

    def load_data(self, ticker, df, change_rate=0.0):
        self.current_ticker = ticker
        self.df = df
        self.current_change_rate = change_rate
        
        # 전처리
        self.df.columns = [c.capitalize() for c in self.df.columns]
        self.df.index.name = 'Date'
        
        # 지표 계산
        self.calculate_indicators()
        
        # 헤더 업데이트
        last_price = self.df['Close'].iloc[-1]
        self.update_header_info(last_price, change_rate)
        
        self.update_plot()

    def update_header_info(self, price, change_rate):
        color_code = "#FF0000" if change_rate > 0 else "#0000FF" if change_rate < 0 else "#FFFFFF"
        self.info_label.setText(f"종목: {self.current_ticker} | 현재가: ${price:,.2f} | <span style='color:{color_code}'>등락률: {change_rate:+.2f}%</span>")

    def calculate_indicators(self):
        if self.df is None or len(self.df) < 5: return

        # 1. 이동평균선 (5, 20, 50, 100, 200)
        for length in [5, 20, 50, 100, 200]:
            self.df[f'MA{length}'] = ta.sma(self.df['Close'], length=length)

        # 2. 윌리엄스 프랙탈
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
        if self.df is None or self.df.empty:
            return

        self.ax.clear()
        
        add_plots = []
        
        colors = {5:'black', 20:'orange', 50:'blue', 100:'green', 200:'red'}
        for length, color in colors.items():
            if f'MA{length}' in self.df.columns:
                 add_plots.append(mpf.make_addplot(self.df[f'MA{length}'], ax=self.ax, color=color, width=1.0))

        if 'Fractal_Up' in self.df.columns:
            add_plots.append(mpf.make_addplot(self.df['Fractal_Up'], ax=self.ax, type='scatter', markersize=50, marker='v', color='blue'))
        if 'Fractal_Down' in self.df.columns:
            add_plots.append(mpf.make_addplot(self.df['Fractal_Down'], ax=self.ax, type='scatter', markersize=50, marker='^', color='red'))

        try:
            mpf.plot(
                self.df, 
                type='candle', 
                style=self.style, 
                ax=self.ax, 
                addplot=add_plots if add_plots else None,
                volume=False,
                warn_too_much_data=10000
            )
            self.canvas.draw()
        except Exception as e:
            print(f"Plot Error: {e}")

    def update_realtime_price(self, price):
        if self.df is None or self.df.empty:
            return

        last_idx = self.df.index[-1]
        
        current_h = self.df.at[last_idx, 'High']
        current_l = self.df.at[last_idx, 'Low']
        
        self.df.at[last_idx, 'Close'] = price
        self.df.at[last_idx, 'High'] = max(current_h, price)
        self.df.at[last_idx, 'Low'] = min(current_l, price)
        
        self.calculate_indicators()
        
        self.update_plot()