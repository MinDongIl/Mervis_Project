import pandas as pd
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
        
        # 차트 스타일 설정
        self.mc = mpf.make_marketcolors(up='red', down='blue', inherit=True)
        self.style = mpf.make_mpf_style(marketcolors=self.mc, gridstyle=':', y_on_right=True)

        self.df = None
        self.current_ticker = None

    def load_data(self, ticker, df, change_rate=0.0):
        """
        메인에서 받아온 DataFrame과 등락률로 차트 그리기
        change_rate 인자 추가됨
        """
        self.current_ticker = ticker
        self.df = df
        
        # DataFrame 전처리 (mplfinance 형식 맞춤)
        self.df.columns = [c.capitalize() for c in self.df.columns]
        self.df.index.name = 'Date'
        
        # 정보 갱신 (등락률 색상 적용)
        last_price = self.df['Close'].iloc[-1]
        
        color_code = "#FF0000" if change_rate > 0 else "#0000FF" if change_rate < 0 else "#FFFFFF"
        self.info_label.setText(f"종목: {ticker} | 현재가: ${last_price:,.2f} | <span style='color:{color_code}'>등락률: {change_rate:+.2f}%</span>")
        
        self.update_plot()

    def update_plot(self):
        if self.df is None or self.df.empty:
            return

        self.ax.clear()
        
        # 차트 그리기
        mpf.plot(
            self.df, 
            type='candle', 
            style=self.style, 
            ax=self.ax, 
            volume=False,
            warn_too_much_data=10000
        )
        self.canvas.draw()

    def update_realtime_price(self, price):
        """
        웹소켓 실시간 가격 수신 시 마지막 봉 업데이트
        """
        if self.df is None or self.df.empty:
            return

        last_idx = self.df.index[-1]
        
        current_h = self.df.at[last_idx, 'High']
        current_l = self.df.at[last_idx, 'Low']
        
        self.df.at[last_idx, 'Close'] = price
        self.df.at[last_idx, 'High'] = max(current_h, price)
        self.df.at[last_idx, 'Low'] = min(current_l, price)
        
        self.update_plot()