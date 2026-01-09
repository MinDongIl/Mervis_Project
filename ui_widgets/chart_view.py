# 파일경로: ui_widgets/chart_view.py
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
        
        # 상단 정보바
        self.info_label = QLabel("종목을 선택해주세요.")
        self.info_label.setStyleSheet("background-color: #34495E; color: white; font-weight: bold; font-size: 12pt; padding: 5px;")
        self.layout.addWidget(self.info_label)

        # 캔버스
        self.fig = Figure(figsize=(10, 6), dpi=100)
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.fig.patch.set_facecolor('#F0F8FF')
        
        self.layout.addWidget(self.canvas)
        
        # 스타일 설정
        self.mc = mpf.make_marketcolors(up='red', down='blue', inherit=True)
        self.style = mpf.make_mpf_style(marketcolors=self.mc, gridstyle=':', y_on_right=True)

        self.df = None # 현재 차트 데이터
        self.current_ticker = None

    def load_data(self, ticker, df):
        """
        [핵심] 메인에서 받아온 DataFrame으로 차트 그리기
        """
        self.current_ticker = ticker
        self.df = df
        
        # DataFrame 전처리 (mplfinance 형식 맞춤)
        # kis_chart에서 오는 컬럼명: ['open', 'high', 'low', 'close', 'volume'] (소문자 가정)
        # mplfinance는 대문자 인덱스 또는 컬럼을 선호하므로 변환
        self.df.columns = [c.capitalize() for c in self.df.columns]
        self.df.index.name = 'Date'
        
        # 정보 갱신
        last_price = self.df['Close'].iloc[-1]
        self.info_label.setText(f"종목: {ticker} (Last: ${last_price:,.2f})")
        
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
            volume=False, # 공간 절약을 위해 볼륨 끔 (필요시 True)
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
        
        # UI 반응성을 위해 매번 그리지 않고 가격 라벨만 바꿀 수도 있음
        # 일단은 즉시 리드로잉
        self.update_plot()